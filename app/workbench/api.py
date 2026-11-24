"""Opt-in, capability-protected loopback API for the local workbench."""

import csv
from hashlib import sha256
from pathlib import Path
import secrets
import sys

from flask import Blueprint, Response, g, jsonify, request

from app.i18n import translate
from app.workbench import code_tools, external, jobs, pdf_preview, tabular, terminal
from app.workbench.files import ACTIVE_ROOT, MAX_TEXT, WORKSPACES, ProjectStore, WorkspaceError, tail

workbench = Blueprint("workbench", __name__, url_prefix="/api/local/v1")


def mount(app, token, directory, *, port=None):
    app.config.setdefault("DEFAULT_INTERFACE_LANGUAGE", "vi")
    store = ProjectStore(directory)
    terminals = terminal.Terminals()
    app.extensions["workbench"] = {
        "store": store,
        "terminals": terminals,
        "token": token,
        "port": port,
        "runs": jobs.Runs(store),
    }
    app.register_blueprint(workbench)
    return app.extensions["workbench"]


def state():
    from flask import current_app

    return current_app.extensions["workbench"]


@workbench.before_request
def authorize():
    config = state()
    expected = f"127.0.0.1:{config['port']}" if config["port"] not in (None, 80) else "127.0.0.1"
    if (
        request.remote_addr != "127.0.0.1"
        or request.host != expected
        or request.headers.get("Origin", f"http://{expected}") != f"http://{expected}"
        or request.headers.get("Sec-Fetch-Site") not in (None, "same-origin")
        or not secrets.compare_digest(
            request.headers.get("Authorization", "").encode(), b"Bearer " + config["token"].encode()
        )
    ):
        raise WorkspaceError("The local session is not authorized.", 403)
    g.workspace = request.headers.get("X-Workspace", "project")
    if g.workspace not in WORKSPACES:
        raise WorkspaceError("Invalid workspace.")
    unscoped = {
        "session_info",
        "select_project",
        "set_feature",
        "start_terminal",
        "terminal_output",
        "terminal_input",
        "close_terminal",
    }
    if request.endpoint.rsplit(".", 1)[-1] not in unscoped:
        g.workbench_root = ACTIVE_ROOT.set(str(authorized_project()))


def authorized_project():
    root = store().workspace_root(g.workspace)
    if request.headers.get("X-Project") != project_id(str(root)):
        raise WorkspaceError("The project changed. Reload the workbench before continuing.", 409)
    return root


@workbench.teardown_request
def release_root(error):
    del error
    if "workbench_root" in g:
        ACTIVE_ROOT.reset(g.pop("workbench_root"))


def project_id(root):
    return sha256(root.encode("utf-8")).hexdigest()


@workbench.after_request
def private(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@workbench.errorhandler(WorkspaceError)
def rejected(error):
    return jsonify(error=error.translated()), error.status


@workbench.errorhandler(OSError)
def inaccessible(error):
    if isinstance(error, FileExistsError):
        return jsonify(error=translate("This name already exists.")), 409
    if isinstance(error, FileNotFoundError):
        return jsonify(error=translate("The file or folder has changed.")), 404
    return jsonify(error=translate("The operating system denied the action or the file is busy.")), 422


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise WorkspaceError("A JSON object is required.")
    return value


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise WorkspaceError("Numeric value is out of range.")
    return value


def store():
    return state()["store"]


def offset():
    value = request.args.get("offset", "0")
    # An unparsable offset is a client error, never a silent restart from 0.
    if not value.isascii() or not value.isdigit() or len(value) > 16:
        raise WorkspaceError("Numeric value is out of range.")
    return integer(int(value), 0, 2**53 - 1)


@workbench.get("/session")
def session_info():
    project = store()
    try:
        root = project.workspace_root(g.workspace)
    except WorkspaceError:
        root = None
    return jsonify(
        root=str(root) if root else None,
        project=project_id(str(root)) if root else None,
        recent=project.workspace_recent(g.workspace),
        shells=list(terminal.profiles()),
        features=project.state["features"],
        os=sys.platform,
    )


@workbench.post("/project")
def select_project():
    root = store().select(body().get("path"), g.workspace)
    return jsonify(
        root=str(root), project=project_id(str(root)), recent=store().workspace_recent(g.workspace)
    )


@workbench.get("/tree")
def tree():
    return jsonify(store().listing(request.args.get("path", ""), offset()))


@workbench.get("/view-state")
def read_view_state():
    return jsonify(store().workspace_view(g.workspace, request.headers["X-Project"]))


@workbench.put("/view-state")
def write_view_state():
    request.max_content_length = 192 * 1024
    return jsonify(store().save_workspace_view(g.workspace, request.headers["X-Project"], body()))


@workbench.get("/tree/search")
def search_tree():
    return jsonify(store().search(request.args.get("q", "")))


@workbench.post("/tree")
def manage_tree():
    values = body()
    store().manage(values.get("path"), values.get("action"), values.get("target"))
    return jsonify(ok=True)


@workbench.get("/file")
def read_file():
    return jsonify(store().read(request.args.get("path", "")))


@workbench.put("/file")
def save_file():
    request.max_content_length = MAX_TEXT * 6 + 4096
    values = body()
    return jsonify(store().write(values.get("path"), values.get("text"), values.get("revision")))


def code_file(values):
    if g.workspace != "code":
        raise WorkspaceError("Open the file in the Code workspace.", 403)
    name = values.get("path")
    path = store().resolve(name)
    if not path.is_file():
        raise WorkspaceError("Choose a file in Code.")
    snapshot = store().read(name)
    if snapshot["revision"] != values.get("revision"):
        raise WorkspaceError("The file changed on disk. Reopen it before continuing.", 409)
    return path, snapshot


@workbench.post("/code/check")
def check_code():
    request.max_content_length = 8_192
    values = body()
    path, snapshot = code_file(values)
    if path.suffix.casefold() != ".py":
        raise WorkspaceError("Choose a Python file.")
    root = store().root()
    result = code_tools.diagnostics(path, root, code_tools.project_python(store(), root), snapshot["text"])
    code_file(values)
    return jsonify(result)


@workbench.post("/code/format")
def format_code():
    request.max_content_length = MAX_TEXT * 6 + 8192
    values = body()
    path, _ = code_file(values)
    root = store().root()
    return jsonify(
        code_tools.format_text(path, root, code_tools.project_python(store(), root), values.get("text"))
    )


@workbench.get("/log")
def read_log():
    file = store().resolve(request.args.get("path", ""))
    if file.suffix.casefold() not in {".log", ".txt", ".jsonl"}:
        raise WorkspaceError("Choose a .log, .txt or .jsonl file.")
    return jsonify(tail(file, offset(), request.args.get("stamp")))


@workbench.get("/pdf")
def read_pdf():
    path = store().resolve(request.args.get("path", ""))
    page = integer(request.args.get("page", type=int), 1, 100_000)
    zoom = integer(request.args.get("zoom", type=int), 75, 200)
    image, count = pdf_preview.render_page(path, page - 1, zoom)
    return Response(
        image, mimetype="image/png", headers={"X-PDF-Pages": str(count), "X-Content-Type-Options": "nosniff"}
    )


@workbench.get("/metrics")
def metrics():
    project = store()
    root = project.root()
    output = {"training": [], "machine": [], "warnings": [], "default_log": None}
    try:
        if project.resolve("train.log").is_file():
            output["default_log"] = "train.log"
    except WorkspaceError:
        pass
    for name, loader, key in (
        ("metrics.csv", jobs.training_metrics, "training"),
        ("machine.jsonl", jobs.machine_metrics, "machine"),
    ):
        if not (root / name).is_file():
            continue
        try:
            text = project.read(name)["text"] if key == "training" else tail(project.resolve(name))["text"]
            output[key] = loader(text)
        except (WorkspaceError, ValueError, csv.Error):
            output["warnings"].append(translate("Could not read {0}.", name))
    if request.args.get("sample") == "1":
        output["live"] = jobs.sample_machine(project.state["features"]["gpu"])
    return jsonify(output)


@workbench.get("/environment")
def environment():
    project = store()
    root = project.root()
    available = jobs.interpreters(root)
    chosen = jobs.runtime_id(project, root, available)
    response = {"interpreters": {key: str(value) for key, value in available.items()}, "selected": chosen}
    if request.args.get("packages") == "1":
        response.update(jobs.package_list(available[chosen], root))
    return jsonify(response)


@workbench.put("/environment")
def select_environment():
    project = store()
    root = project.root()
    selected = body().get("interpreter")
    if not isinstance(selected, str) or selected not in jobs.interpreters(root):
        raise WorkspaceError("The interpreter is not in the project.")
    with project.edit_profile() as profile:
        profile["interpreters"][str(root)] = selected
    return jsonify(selected=selected)


@workbench.put("/features")
def set_feature():
    values = body()
    feature, enabled = values.get("feature"), values.get("enabled")
    project = store()
    with project.edit_profile() as profile:
        current = profile["features"]
        if not isinstance(feature, str) or feature not in current or type(enabled) is not bool:
            raise WorkspaceError("Invalid extension.")
        current[feature] = enabled
    return jsonify(features=current)


@workbench.post("/terminals")
def start_terminal():
    values = body()
    shell = values.get("shell")
    if not isinstance(shell, str):
        raise WorkspaceError("Choose a shell.")
    interpreter = None
    if shell == "SSH":
        root = authorized_project()
        if not store().state["features"]["ssh"]:
            raise WorkspaceError("The SSH extension is off.", 403)
        command = terminal.ssh_command(values.get("host"), values.get("user"), values.get("port", 22))
    elif shell == "Run File":
        root = authorized_project()
        g.workbench_root = ACTIVE_ROOT.set(str(root))
        script, _ = code_file(values)
        interpreter = code_tools.project_python(store(), root)
        command = code_tools.script_command(script, interpreter)
    elif shell == "Python Debug":
        root = authorized_project()
        script = store().resolve(values.get("path", ""), root=root)
        if not script.is_file() or script.suffix.casefold() != ".py":
            raise WorkspaceError("Choose a Python file in the project to debug.")
        available = jobs.interpreters(root)
        interpreter = available[jobs.runtime_id(store(), root, available)]
        command = [str(interpreter), "-I", "-u", "-m", "pdb", str(script)]
    else:
        scoped = "X-Project" in request.headers
        root = authorized_project() if scoped else Path.home()
        command = terminal.profiles().get(shell)
        if not command:
            raise WorkspaceError("Shell is unavailable.")
        available = jobs.interpreters(root)
        interpreter = available[jobs.runtime_id(store(), root, available) if scoped else "app"]
    session = state()["terminals"].add(command, root, interpreter)
    return jsonify(
        id=session,
        cwd=str(root) if shell != "SSH" else None,
        interpreter=str(interpreter) if interpreter is not None else None,
    ), 201


@workbench.get("/ports")
def listening_ports():
    import psutil

    try:
        sockets = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, NotImplementedError) as error:
        raise WorkspaceError(
            "The operating system has not granted permission to read TCP ports.", 403
        ) from error
    rows = sorted(
        {
            (conn.status != psutil.CONN_LISTEN, conn.laddr.port, conn.laddr.ip, conn.pid or 0)
            for conn in sockets
            if conn.laddr and not conn.raddr and conn.status in (psutil.CONN_LISTEN, psutil.CONN_NONE)
        }
    )
    return jsonify(
        ports=[
            {"address": ip, "port": port, "pid": pid or None, "status": "unknown" if unknown else "listening"}
            for unknown, port, ip, pid in rows[:200]
        ],
        truncated=len(rows) > 200,
    )


@workbench.get("/terminals/<session_id>")
def terminal_output(session_id):
    wait_ms = request.args.get("wait_ms", type=int) if "wait_ms" in request.args else 0
    if wait_ms is None or not 0 <= wait_ms <= 600:
        raise WorkspaceError("Invalid terminal wait time.")
    return jsonify(state()["terminals"].get(session_id).snapshot(offset(), wait_ms))


@workbench.post("/terminals/<session_id>")
def terminal_input(session_id):
    session = state()["terminals"].get(session_id)
    values = body()
    if "text" in values:
        text = values["text"]
        if not isinstance(text, str) or not text or len(text) > 32768:
            raise WorkspaceError("Invalid terminal input.")
        session.write(text)
    elif "rows" in values and "columns" in values:
        session.resize(integer(values["rows"], 2, 180), integer(values["columns"], 2, 400))
    else:
        raise WorkspaceError("Invalid terminal action.")
    return "", 204


@workbench.delete("/terminals/<session_id>")
def close_terminal(session_id):
    state()["terminals"].close(session_id)
    return "", 204


@workbench.route("/runs", methods=["GET", "POST"])
def runs():
    root = store().root()
    runner = state()["runs"]
    if request.method == "GET":
        return jsonify(runs=runner.recent(root))
    values = body()
    return jsonify(
        runner.start(
            secrets.token_hex(16),
            root,
            values.get("script"),
            values.get("args", []),
            values.get("config_files", []),
        )
    ), 201


@workbench.get("/runs/<run_id>")
def run_output(run_id):
    return jsonify(state()["runs"].output(run_id, store().root(), offset(), request.args.get("stamp")))


@workbench.post("/runs/attach")
def attach_run():
    return jsonify(state()["runs"].attach(store().root(), body()))


@workbench.get("/runs/compare")
def compare_runs():
    return jsonify(
        state()["runs"].compare(request.args.get("left"), request.args.get("right"), store().root())
    )


@workbench.get("/runs/<run_id>/profile")
def run_profile(run_id):
    return jsonify(state()["runs"].profile(run_id, store().root()))


@workbench.post("/runs/<run_id>/stop")
def stop_run(run_id):
    state()["runs"].stop(run_id, store().root())
    return "", 204


@workbench.post("/external")
def external_preview():
    if not store().state["features"]["external_parsers"]:
        raise WorkspaceError("The file analysis extension is off.", 403)
    values = body()
    path = values.get("path")
    format_name = values.get("format")
    if not isinstance(format_name, str):
        raise WorkspaceError("Choose a file format.")
    if format_name == "parquet":
        file = store().resolve(path)
        if file.suffix.casefold() != ".parquet" or not file.is_file():
            raise WorkspaceError("Choose a .parquet file in the project.", 422)
        return jsonify(tabular.parquet_profile(file))
    content = store().read(path)["text"]
    if format_name in ("csv", "jsonl"):
        return jsonify(tabular.text_profile(content, format_name))
    legacy_formats = {"csv-log": "csv", "jsonl-log": "jsonl"}
    try:
        return jsonify(
            external.analyze(content, legacy_formats.get(format_name, format_name), values.get("unit"))
        )
    except csv.Error:
        raise WorkspaceError("CSV syntax is invalid.", 422) from None
