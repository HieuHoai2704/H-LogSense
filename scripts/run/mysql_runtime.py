"""Portable operator lifecycle for an owned MySQL ZIP runtime. No service/drop.

    python -m scripts.run.mysql_runtime status
    python -m scripts.run.mysql_runtime stop
    python -m scripts.run.mysql_runtime start
    python -m scripts.run.mysql_runtime backup --schema logsense_dev --output .local/dev.sql
    python -m scripts.run.mysql_runtime restore --input .local/dev.sql
    python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev

Provision an official native MySQL 8.4 distribution first. This tool does not
download executables, install services, change global config or reuse databases.
"""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time

import pymysql

from app.permissions import check_private, open_private, write_private


def owned_root(value):
    root = Path(value).resolve()
    allowed = (Path(__file__).resolve().parents[2] / ".local").resolve()
    if not root.is_relative_to(allowed) or root == allowed:
        raise ValueError(
            "Runtime must be a dedicated directory beneath project .local."
        )
    return root


def private_write(path, text):
    # Owner-only from creation, atomic (a crash never truncates the only copy of the credentials)
    # and verified: chmod is ignored on filesystems without POSIX modes.
    write_private(path, text)


def load(root):
    info = json.loads((root / "private.json").read_text())
    if not re.fullmatch(r"[0-9a-f]{32}", info["owner"]):
        raise ValueError("Invalid runtime ownership marker.")
    return info


def connect(info):
    return pymysql.connect(
        host="127.0.0.1",
        port=info.get("port", 13306),
        user="root",
        password=info["root_password"],
        charset="utf8mb4",
        connect_timeout=3,
    )


def hidden_options():
    return (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )


def binary(root, info, name):
    base = Path(info["basedir"]).resolve()
    suffix = ".exe" if os.name == "nt" else ""
    path = base / "bin" / (name + suffix)
    if not path.is_file():
        raise ValueError(
            "Native MySQL binary missing; use the distribution for this operating system/CPU."
        )
    return str(path)


def status(root):
    info = load(root)
    with connect(info) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT VERSION(),@@port,@@datadir,@@bind_address,@@time_zone")
        version, port, datadir, bind, zone = cursor.fetchone()
        if Path(datadir).resolve() != (root / "data").resolve() or bind != "127.0.0.1":
            raise ValueError("Server ownership or bind-address mismatch.")
        return dict(
            status="ready",
            mysql=version,
            port=port,
            bind_address=bind,
            time_zone=zone,
            datadir_is_owned=True,
        )


def start(root):
    info = load(root)
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", info.get("port", 13306))) == 0:
            return status(root)
    args = [binary(root, info, "mysqld"), "--defaults-file=" + str(root / "my.ini")]
    if not info.get("bootstrapped"):
        args.append("--init-file=" + str(root / "bootstrap.sql"))
    # Explicit config path is one argv value on Windows and POSIX (spaces safe).
    with (root / "launcher.log").open("ab") as log:
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **hidden_options()
        )
    for _ in range(30):
        if process.poll() is not None:
            raise RuntimeError(
                "MySQL exited during startup; inspect private server log."
            )
        try:
            result = status(root)
            info.update(bootstrapped=True, pid=process.pid)
            private_write(root / "private.json", json.dumps(info))
            private_write(
                root / "bootstrap.sql",
                "-- Bootstrap completed; no reusable SQL credentials here.\n",
            )
            return result
        except (pymysql.MySQLError, OSError):
            time.sleep(0.25)
    raise RuntimeError("MySQL startup timed out; inspect private logs.")


def stop(root):
    info = load(root)
    status(root)  # Authenticate and verify datadir before issuing shutdown.
    with connect(info) as connection, connection.cursor() as cursor:
        cursor.execute("SHUTDOWN")
    for _ in range(60):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", info.get("port", 13306))) != 0:
                return {"status": "stopped", "shutdown": "graceful SQL SHUTDOWN"}
        time.sleep(0.25)
    raise RuntimeError("Shutdown not confirmed; do not kill unrelated processes.")


def grant_dataset_crud(root, schema):
    """Grant DELETE on two metadata tables, never on the complete schema.

    Migrations must already have created both tables. This operator command
    changes privileges only; it never deletes data or broadens raw-log access.
    """
    if not isinstance(schema, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", schema):
        raise ValueError("Use a bounded alphanumeric/underscore schema name.")
    root = owned_root(root)
    ready = status(root)  # Authenticate and verify the protected datadir/binding.
    info = load(root)
    if ready["port"] != info.get("port", 13306):
        raise ValueError("Server port does not match the owned runtime.")
    tables = ("datasets", "user_datasets")
    with connect(info) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.tables "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s) "
            "AND TABLE_TYPE='BASE TABLE'",
            (schema, *tables),
        )
        if {row[0] for row in cursor.fetchall()} != set(tables):
            raise ValueError("Apply dataset/auth migrations before granting CRUD privileges.")
        # GRANT is DCL and auto-commits in MySQL. Both table names are fixed;
        # the sole interpolated schema identifier was validated above. Repeating
        # these same grants is safe if an earlier connection was interrupted.
        for table in tables:
            cursor.execute(
                f"GRANT DELETE ON `{schema}`.`{table}` TO 'logsense_app'@'localhost'"
            )
    return {
        "status": "granted",
        "schema": schema,
        "account": "logsense_app@localhost",
        "privilege": "DELETE",
        "tables_granted": list(tables),
        "data_deleted": False,
    }


def backup(root, schema, output):
    if not re.fullmatch(
        r"logsense_(dev|test_[0-9a-f]{12}|bench_[0-9a-f]{12}|restore_[0-9a-f]{12})",
        schema,
    ):
        raise ValueError("Schema name is outside the owned namespace.")
    status(root)
    info = load(root)
    destination = owned_root(output)
    if destination.is_relative_to(Path(root).resolve()):
        raise ValueError("Write backups outside the runtime directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MYSQL_PWD=info["root_password"])
    args = [
        binary(root, info, "mysqldump"),
        "--host=127.0.0.1",
        "--port=" + str(info.get("port", 13306)),
        "--user=root",
        "--single-transaction",
        "--no-tablespaces",
        "--skip-lock-tables",
        "--set-gtid-purged=OFF",
        "--skip-add-drop-table",
        "--skip-add-locks",
        "--hex-blob",
        "--skip-triggers",
        schema,
    ]
    with open_private(destination) as output_file:  # owner-only before mysqldump writes any row
        result = subprocess.run(
            args,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output_file,
            stderr=subprocess.PIPE,
            **hidden_options(),
        )
    if result.returncode:
        raise RuntimeError(
            "Backup failed; incomplete output retained, never restored automatically."
        )
    from app.services.bgl_ingestion import fingerprint

    result = {
        "status": "backed_up",
        "schema": schema,
        "bytes": destination.stat().st_size,
        "sha256": fingerprint(destination),
    }
    private_write(
        destination.with_suffix(destination.suffix + ".manifest.json"),
        json.dumps(result),
    )
    return result


def restore(root, input_file):
    info = load(root)
    status(root)
    source = owned_root(input_file)
    from app.services.bgl_ingestion import fingerprint

    manifest = json.loads(
        source.with_suffix(source.suffix + ".manifest.json").read_text()
    )
    if manifest.get("sha256") != fingerprint(source):
        raise ValueError("Backup checksum does not match its manifest.")
    # An operator-created dump is still executed with a NEW narrowly scoped user.
    # It cannot modify any existing schema even if the input is tampered with.
    schema = "logsense_restore_" + secrets.token_hex(6)
    user = "ls_restore_" + secrets.token_hex(6)
    password = secrets.token_hex(32)
    with connect(info) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
        )
        cursor.execute(
            f"CREATE USER '{user}'@'localhost' IDENTIFIED BY %s", (password,)
        )
        cursor.execute(
            f"GRANT SELECT,INSERT,UPDATE,CREATE,ALTER,INDEX,REFERENCES ON `{schema}`.* TO '{user}'@'localhost'"
        )
    private_write(
        root / (schema + ".private.json"),
        json.dumps({"schema": schema, "user": user, "password": password}),
    )
    env = dict(os.environ, MYSQL_PWD=password)
    args = [
        binary(root, info, "mysql"),
        "--host=127.0.0.1",
        "--port=" + str(info.get("port", 13306)),
        "--user=" + user,
        "--binary-mode=1",
        schema,
    ]
    with source.open("rb") as stream:
        result = subprocess.run(
            args,
            env=env,
            stdin=stream,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **hidden_options(),
        )
    if result.returncode:
        raise RuntimeError(
            "Restore failed in a new schema; existing schemas were not reset."
        )
    return {
        "status": "restored",
        "new_schema": schema,
        "source_bytes": source.stat().st_size,
    }


def initialize(root, basedir, port):
    if root.exists():
        raise ValueError("Refusing to initialize over an existing runtime directory.")
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid local port.")
    if any(
        character in str(root) + str(basedir) for character in ("\n", "\r", '"', "\x00")
    ):
        raise ValueError("Unsupported characters in a MySQL configuration path.")
    if os.name != "nt" and len(str(root / "mysql.sock").encode()) > 100:
        raise ValueError(
            "Choose a shorter project/runtime path for the native Unix socket."
        )
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise ValueError("Port is already in use.")
    root.mkdir(parents=True, mode=0o700)
    check_private(root)
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami"], capture_output=True, text=True, check=True
        ).stdout.strip()
        subprocess.run(
            [
                "icacls",
                str(root),
                "/inheritance:r",
                "/grant:r",
                identity + ":(OI)(CI)F",
                "SYSTEM:(OI)(CI)F",
            ],
            capture_output=True,
            check=True,
        )
    info = dict(
        owner=secrets.token_hex(16),
        root_password=secrets.token_hex(32),
        app_password=secrets.token_hex(32),
        migrator_password=secrets.token_hex(32),
        basedir=str(Path(basedir).resolve()),
        port=port,
        bootstrapped=False,
    )
    private_write(root / "private.json", json.dumps(info))
    configuration = (
        "[mysqld]\n"
        + "\n".join(
            [
                'basedir="' + Path(info["basedir"]).as_posix() + '"',
                'datadir="' + (root / "data").as_posix() + '"',
                "bind-address=127.0.0.1",
                f"port={port}",
                "mysqlx=0",
                "innodb-buffer-pool-size=128M",
                "character-set-server=utf8mb4",
                "collation-server=utf8mb4_0900_as_cs",
                "default-time-zone=+00:00",
                'log-error="' + (root / "server-error.log").as_posix() + '"',
                'pid-file="' + (root / "server.pid").as_posix() + '"',
            ]
        )
        + "\n"
    )
    if os.name != "nt":
        configuration += 'socket="' + (root / "mysql.sock").as_posix() + '"\n'
    private_write(root / "my.ini", configuration)
    private_write(
        root / "bootstrap.sql",
        "ALTER USER 'root'@'localhost' IDENTIFIED BY '" + info["root_password"] + "';\n"
        "CREATE DATABASE logsense_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs;\n"
        "CREATE USER 'logsense_app'@'localhost' IDENTIFIED BY '"
        + info["app_password"]
        + "';\n"
        "GRANT SELECT,INSERT,UPDATE ON logsense_dev.* TO 'logsense_app'@'localhost';\n"
        "CREATE USER 'logsense_migrator'@'localhost' IDENTIFIED BY '"
        + info["migrator_password"]
        + "';\n"
        "GRANT SELECT,INSERT,UPDATE,CREATE,ALTER,INDEX,REFERENCES ON logsense_dev.* TO 'logsense_migrator'@'localhost';\n",
    )
    # Initialization has no network listener. First start sets the random password
    # using init-file before the local server accepts connections.
    result = subprocess.run(
        [
            binary(root, info, "mysqld"),
            "--defaults-file=" + str(root / "my.ini"),
            "--initialize-insecure",
        ],
        capture_output=True,
        **hidden_options(),
    )
    if result.returncode:
        raise RuntimeError(
            "Initialization failed; inspect private logs, do not reinitialize in place."
        )
    return {"status": "initialized", "port": port, "next": "start"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".local/mysql-foundation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "stop", "status"):
        sub.add_parser(name)
    initial = sub.add_parser("init")
    initial.add_argument("--basedir", required=True)
    initial.add_argument("--port", type=int, default=13306)
    dump = sub.add_parser("backup")
    dump.add_argument("--schema", required=True)
    dump.add_argument("--output", required=True)
    restored = sub.add_parser("restore")
    restored.add_argument("--input", required=True)
    dataset_grant = sub.add_parser(
        "grant-dataset-crud", help="Grant DELETE only on migrated dataset/ACL metadata tables"
    )
    dataset_grant.add_argument("--schema", required=True)
    execute = sub.add_parser(
        "exec", help="Run this venv Python with a private, process-local DATABASE_URL"
    )
    execute.add_argument("--role", choices=["app", "migrate"], default="app")
    execute.add_argument("python_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = owned_root(args.root)
    if args.command == "init":
        result = initialize(root, args.basedir, args.port)
    elif args.command == "backup":
        result = backup(root, args.schema, args.output)
    elif args.command == "restore":
        result = restore(root, args.input)
    elif args.command == "grant-dataset-crud":
        result = grant_dataset_crud(root, args.schema)
    elif args.command == "exec":
        from sqlalchemy.engine import URL

        info = load(root)
        arguments = (
            args.python_args[1:] if args.python_args[:1] == ["--"] else args.python_args
        )
        if not arguments:
            raise ValueError("Python arguments required after --.")
        role = "logsense_app" if args.role == "app" else "logsense_migrator"
        password = info["app_password" if args.role == "app" else "migrator_password"]
        env = dict(os.environ)
        env["DATABASE_URL"] = URL.create(
            "mysql+pymysql",
            username=role,
            password=password,
            host="127.0.0.1",
            port=info.get("port", 13306),
            database="logsense_dev",
        ).render_as_string(hide_password=False)
        if not info.get("flask_secret_key"):
            info["flask_secret_key"] = secrets.token_hex(32)
            private_write(root / "private.json", json.dumps(info))
        env["FLASK_SECRET_KEY"] = info["flask_secret_key"]
        raise SystemExit(subprocess.call([sys.executable, *arguments], env=env))
    else:
        result = {"status": status, "start": start, "stop": stop}[args.command](root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(
            "Local MySQL operation failed ("
            + type(error).__name__
            + "); inspect private diagnostics."
        ) from None
