"""Explicit, project-scoped editor tools with bounded results."""

import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryFile
from threading import BoundedSemaphore

from .files import MAX_TEXT, WorkspaceError
from .jobs import NO_WINDOW, interpreters, runtime_id
from .terminal import terminal_environment

_TOOL_SLOTS = BoundedSemaphore(2)
_NODE_TOOLS = {"Pyright": ("pyright", "index.js"), "Prettier": ("prettier", "bin", "prettier.cjs")}
_PRETTIER_SUFFIXES = {".js", ".ts", ".json", ".css", ".html", ".md", ".yaml", ".yml"}


def project_python(store, root):
    available = interpreters(root)
    return available[runtime_id(store, root, available)]


def node_command():
    node = shutil.which("node.exe" if NO_WINDOW else "node")
    if not node:
        raise WorkspaceError("Cần Node.js trên PATH để chạy JavaScript hoặc công cụ npm.", 422)
    return node


def node_tool(root, name):
    try:
        entry = root.joinpath("node_modules", *_NODE_TOOLS[name]).resolve(strict=True)
        if not entry.is_relative_to(root) or not entry.is_file():
            raise FileNotFoundError
    except (OSError, RuntimeError):
        raise WorkspaceError(f"Cài {name} trong dự án bằng npm install -D {name.lower()}.", 422) from None
    return [node_command(), str(entry)]


def run_tool(command, root, interpreter, name, *, text=None, valid_codes=(0,)):
    if not _TOOL_SLOTS.acquire(blocking=False):
        raise WorkspaceError("Công cụ đang bận. Thử lại sau.", 429)
    try:
        with TemporaryFile() as output, TemporaryFile() as errors:
            result = subprocess.run(
                command, cwd=root, env=terminal_environment(interpreter), creationflags=NO_WINDOW,
                input=text.encode("utf-8") if text is not None else b"", stdout=output, stderr=errors,
                timeout=15, check=False,
            )
            output.seek(0)
            data = output.read(2 * MAX_TEXT + 1)
            errors.seek(0)
            error = errors.read(8_192).decode("utf-8", errors="replace")
        if len(data) > 2 * MAX_TEXT:
            raise WorkspaceError(f"Đầu ra {name} vượt giới hạn.", 422)
        if result.returncode not in valid_codes:
            if name == "Ruff" and "No module named ruff" in error:
                raise WorkspaceError("Cài Ruff trong Python đang chọn bằng python -m pip install ruff.", 422)
            raise WorkspaceError(f"{name} không hoàn tất. Kiểm tra cú pháp và cấu hình của dự án.", 422)
        return data.decode("utf-8")
    except subprocess.TimeoutExpired:
        raise WorkspaceError(f"{name} vượt giới hạn 15 giây.", 504) from None
    except (OSError, UnicodeError):
        raise WorkspaceError(f"Không đọc được đầu ra của {name}.", 422) from None
    finally:
        _TOOL_SLOTS.release()


def script_command(path, interpreter):
    if path.suffix.casefold() == ".py":
        return [str(interpreter), "-u", str(path)]
    if path.suffix.casefold() == ".js":
        return [node_command(), str(path)]
    raise WorkspaceError("Chạy trực tiếp hỗ trợ tệp .py và .js.")


def format_text(path, root, interpreter, text):
    if not isinstance(text, str) or "\0" in text:
        raise WorkspaceError("Cần nội dung văn bản UTF-8 hợp lệ.")
    try:
        if len(text.encode("utf-8")) > MAX_TEXT:
            raise WorkspaceError("Nội dung vượt giới hạn 1 MiB.", 413)
    except UnicodeEncodeError:
        raise WorkspaceError("Cần nội dung văn bản UTF-8 hợp lệ.") from None
    suffix = path.suffix.casefold()
    if suffix == ".py":
        tool = "Ruff"
        command = [str(interpreter), "-I", "-m", "ruff", "format", "--no-cache", "--stdin-filename", str(path), "-"]
    elif suffix in _PRETTIER_SUFFIXES:
        tool = "Prettier"
        command = [*node_tool(root, tool), "--stdin-filepath", str(path)]
    else:
        raise WorkspaceError("Định dạng chưa hỗ trợ loại tệp này.")
    formatted = run_tool(command, root, interpreter, tool, text=text)
    if len(formatted.encode("utf-8")) > MAX_TEXT:
        raise WorkspaceError("Nội dung đã định dạng vượt giới hạn 1 MiB.", 422)
    return {"text": formatted.replace("\r\n", "\n"), "tool": tool}


def ruff_issues(data, lines):
    for item in data:
        location = item["location"]
        line = location["row"]
        # Ruff counts Unicode code points; textarea selection uses UTF-16 code units.
        prefix = lines[line - 1][:location["column"] - 1] if 1 <= line <= len(lines) else ""
        yield {"line": line, "column": len(prefix.encode("utf-16-le")) // 2 + 1, "tool": "Ruff",
               "rule": item.get("code"), "severity": item.get("severity", "error"),
               "message": item["message"][:800]}


def pyright_issues(data, path):
    for item in data["generalDiagnostics"]:
        if Path(item.get("file") or "").resolve() != path or "range" not in item:
            continue
        start = item["range"]["start"]
        yield {"line": start["line"] + 1, "column": start["character"] + 1, "tool": "Pyright",
               "rule": item.get("rule"), "severity": item["severity"], "message": item["message"][:800]}


def diagnostics(path, root, interpreter, text):
    tools = ("Ruff", "Pyright")
    issues, completed, unavailable = [], [], {}
    for name in tools:
        try:
            if name == "Ruff":
                command = [str(interpreter), "-I", "-m", "ruff", "check", "--no-cache", "--output-format", "json", "--", str(path)]
            else:
                command = [*node_tool(root, name), "--outputjson", "--pythonpath", str(interpreter), str(path)]
            data = json.loads(run_tool(command, root, interpreter, name, valid_codes=(0, 1)))
            found = ruff_issues(data, text.split("\n")) if name == "Ruff" else pyright_issues(data, path)
            issues.extend(list(found))
            completed.append(name)
        except WorkspaceError as error:
            unavailable[name] = str(error)
        except (ValueError, KeyError, TypeError):
            unavailable[name] = f"Không đọc được kết quả từ {name}."
    issues.sort(key=lambda item: (item["line"], item["column"], item["tool"]))
    return {"issues": issues[:100], "total": len(issues), "completed": completed, "unavailable": unavailable}
