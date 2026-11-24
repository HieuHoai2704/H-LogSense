"""One-command demonstration environment: MySQL in Docker, demo accounts, real BGL data, open the app.

    python -m scripts.run.demo             # start (first run: create, migrate, seed) and open the desktop app
    python -m scripts.run.demo --browser   # same, in the default browser
    python -m scripts.run.demo accounts    # print the demo accounts again
    python -m scripts.run.demo stop        # stop the MySQL container (data is kept)

The first run creates a Docker container ``hlogsen-demo-mysql`` (MySQL 8.4, 127.0.0.1:3308 only) with a
named volume, generates every password, and keeps them owner-only in ``.local/demo/``. It then applies the
Alembic migrations, creates one account per role, imports the first lines of ``data/raw/BGL.zip`` (when
present) and runs the rule and Isolation Forest window detectors through the same API and worker as
production. Later runs reuse everything and only start the container and the app.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE = REPO_ROOT / ".local" / "demo"
CONTAINER = "hlogsen-demo-mysql"
VOLUME = "hlogsen-demo-data"
IMAGE = "mysql:8.4"
PORT = 3308
SCHEMA = "logsense_demo"
ACCOUNTS = (
    # username, role, email: one account per role for the demonstration.
    ("admin", "admin", "admin@demo.h-logsen.local"),
    ("manager", "manager", "manager@demo.h-logsen.local"),
    ("analyst", "analyst", "analyst@demo.h-logsen.local"),
    ("staff", "viewer", "staff@demo.h-logsen.local"),
)
DEMO_LINES = 60000


def say(message):
    print(f"H-logsen demo: {message}", flush=True)


def docker(*args, check=True, capture=True):
    return subprocess.run(
        ["docker", *args], check=check, capture_output=capture, text=True, encoding="utf-8", errors="replace"
    )


def load_state():
    from app.permissions import check_private

    path = STATE / "demo.json"
    if not path.exists():
        return None
    if not check_private(path):
        raise SystemExit(f"{path} must be readable only by you.")
    return json.loads(path.read_text("utf-8"))


def save_state(state):
    from app.permissions import make_private_dir, write_private

    make_private_dir(STATE)
    write_private(STATE / "demo.json", json.dumps(state, indent=2))


def url(state, role="app"):
    from sqlalchemy.engine import URL

    user, password = (
        ("root", state["root_password"]) if role == "admin" else ("logsense_app", state["app_password"])
    )
    return URL.create(
        "mysql+pymysql", username=user, password=password, host="127.0.0.1", port=PORT, database=SCHEMA
    ).render_as_string(hide_password=False)


def container_state():
    result = docker("inspect", "-f", "{{.State.Running}}", CONTAINER, check=False)
    if result.returncode:
        return None
    return result.stdout.strip() == "true"


def ensure_docker():
    if shutil.which("docker") is None:
        raise SystemExit("Docker is required for the demo environment. Install Docker and try again.")
    if docker("info", check=False).returncode:
        raise SystemExit("Docker is installed but not running (or you lack access). Start Docker first.")


def start_mysql(state):
    running = container_state()
    if running is None:
        say(f"creating the MySQL container {CONTAINER} (127.0.0.1:{PORT})")
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                CONTAINER,
                "-p",
                f"127.0.0.1:{PORT}:3306",
                "-v",
                f"{VOLUME}:/var/lib/mysql",
                "-e",
                "MYSQL_ROOT_PASSWORD",  # value comes from the environment, never the command line
                IMAGE,
                "--character-set-server=utf8mb4",
                "--collation-server=utf8mb4_0900_as_cs",
                "--default-time-zone=+00:00",
            ],
            check=True,
            capture_output=True,
            env={**os.environ, "MYSQL_ROOT_PASSWORD": state["root_password"]},
        )
    elif not running:
        say("starting the MySQL container")
        docker("start", CONTAINER)
    import pymysql

    deadline = time.monotonic() + 180
    while True:
        try:
            pymysql.connect(
                host="127.0.0.1", port=PORT, user="root", password=state["root_password"], connect_timeout=3
            ).close()
            return
        except pymysql.MySQLError:
            if time.monotonic() > deadline:
                raise SystemExit(
                    "MySQL did not become ready in 3 minutes; see `docker logs hlogsen-demo-mysql`."
                ) from None
            time.sleep(2)


def provision(state):
    """Schema and a least-privilege application account (idempotent)."""
    import pymysql

    with (
        pymysql.connect(
            host="127.0.0.1", port=PORT, user="root", password=state["root_password"]
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{SCHEMA}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
        )
        cursor.execute(
            "CREATE USER IF NOT EXISTS 'logsense_app'@'%%' IDENTIFIED BY %s", (state["app_password"],)
        )
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE ON `{SCHEMA}`.* TO 'logsense_app'@'%'")


def migrate(state):
    say("applying database migrations")
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app", "db", "upgrade"],
        cwd=REPO_ROOT,
        check=True,
        env={**os.environ, "DATABASE_URL": url(state, "admin")},
        capture_output=True,
    )
    import pymysql

    with (
        pymysql.connect(
            host="127.0.0.1", port=PORT, user="root", password=state["root_password"]
        ) as connection,
        connection.cursor() as cursor,
    ):
        # Deleting is limited to the tables whose pages offer it.
        for table in ("datasets", "user_datasets", "users"):
            cursor.execute(f"GRANT DELETE ON `{SCHEMA}`.`{table}` TO 'logsense_app'@'%'")


def seed(state):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from werkzeug.security import generate_password_hash

    os.environ["DATABASE_URL"] = url(state)
    from app import create_app
    from app.domain import User, UserDataset
    from app.extensions import db
    from app.models import Dataset, DataSource

    app = create_app({"SECRET_KEY": secrets.token_hex(32), "LOGIN_REQUIRED": True})
    passwords = state.setdefault("accounts", {})
    with app.app_context(), Session(db.engine) as session, session.begin():
        for username, role, email in ACCOUNTS:
            if session.scalar(select(User.id).where(User.username == username)) is None:
                password = passwords.setdefault(username, "Demo-" + secrets.token_urlsafe(9))
                session.add(
                    User(
                        username=username,
                        email=email,
                        role=role,
                        password_hash=generate_password_hash(password),
                        active=True,
                        auth_version=1,
                    )
                )
        source = session.scalar(select(DataSource).where(DataSource.source_key == "loghub-bgl"))
        if source is None:
            source = DataSource(source_key="loghub-bgl", name="Loghub BGL")
            session.add(source)
            session.flush()
        dataset = session.scalar(select(Dataset).where(Dataset.dataset_key == "bgl-demo"))
        if dataset is None:
            dataset = Dataset(source_id=source.id, dataset_key="bgl-demo", name="BGL demo", data_mode="real")
            session.add(dataset)
            session.flush()
        dataset_id = dataset.id
        for user in session.scalars(select(User).where(User.username.in_([a[0] for a in ACCOUNTS]))):
            if not session.scalar(
                select(UserDataset.id).where(
                    UserDataset.user_id == user.id, UserDataset.dataset_id == dataset_id
                )
            ):
                session.add(UserDataset(user_id=user.id, dataset_id=dataset_id))
    save_state(state)
    write_accounts(state)

    archive = REPO_ROOT / "data" / "raw" / "BGL.zip"
    if not archive.is_file():
        say(
            "data/raw/BGL.zip not found: the BGL dataset stays empty (upload a file from Dataset management)."
        )
        return
    from app.services.bgl_ingestion import ingest_bgl
    from scripts.run.worker import run_once

    with app.app_context():
        say(f"importing the first {DEMO_LINES:,} BGL lines (about a minute)")
        ingest_bgl(db.engine, dataset_id, str(archive), limit=DEMO_LINES)
        client = app.test_client()
        signed = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": state["accounts"]["admin"]}
        )
        headers = {"X-CSRF-Token": signed.json["csrf_token"]}
        for kind in ("rule", "isolation_forest"):
            say(f"running the {kind.replace('_', ' ')} window detector")
            queued = client.post(
                "/api/v1/detection/jobs",
                json={
                    "dataset_id": dataset_id,
                    "idempotency_key": "demo-" + kind,
                    "configuration": {"detector": kind, "window_seconds": 300, "seed": 42},
                },
                headers=headers,
            )
            if queued.status_code not in (200, 202):
                say(f"the {kind} job was not queued ({queued.status_code}); continuing")
            while run_once(db.engine):
                pass
    state["seeded"] = True
    save_state(state)


def write_accounts(state):
    from app.permissions import write_private

    lines = ["H-logsen demo accounts (local demonstration only)", ""]
    for username, role, email in ACCOUNTS:
        lines.append(f"{role:<8} {username:<8} {state['accounts'][username]:<20} {email}")
    lines += ["", "Staff sign-in: viewer/analyst. Administrator sign-in: manager/admin."]
    write_private(STATE / "accounts.txt", "\n".join(lines) + "\n")


def show_accounts(state):
    print()
    print("  Role      Username  Password              Portal")
    for username, role, _ in ACCOUNTS:
        portal = "Administrator" if role in ("admin", "manager") else "Staff"
        print(f"  {role:<9} {username:<9} {state['accounts'][username]:<21} {portal}")
    print(f"\n  Saved owner-only in {STATE / 'accounts.txt'}")
    print("  Emails (welcome, password reset) are written to ~/.h-logsen/outbox unless SMTP_ENABLED=1.\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", nargs="?", default="start", choices=["start", "accounts", "stop"])
    parser.add_argument("--browser", action="store_true", help="Open in the default browser instead.")
    parser.add_argument("--no-open", action="store_true", help="Prepare everything but do not open the app.")
    args = parser.parse_args(argv)
    os.chdir(REPO_ROOT)
    state = load_state()
    if args.command == "accounts":
        if not state or not state.get("accounts"):
            raise SystemExit("No demo environment yet. Run: python -m scripts.run.demo")
        show_accounts(state)
        return
    ensure_docker()
    if args.command == "stop":
        if container_state():
            docker("stop", CONTAINER)
        say("MySQL stopped; data is kept for the next run.")
        return
    if state is None:
        if docker("volume", "inspect", VOLUME, check=False).returncode == 0:
            raise SystemExit(
                f"The Docker volume {VOLUME} exists but its passwords are missing from .local/demo. "
                f"Remove it with `docker rm -f {CONTAINER}; docker volume rm {VOLUME}` to start fresh."
            )
        state = {"root_password": secrets.token_urlsafe(24), "app_password": secrets.token_urlsafe(24)}
        save_state(state)
    start_mysql(state)
    provision(state)
    migrate(state)
    if not state.get("seeded"):
        seed(state)
    show_accounts(state)
    if args.no_open:
        say(f"ready. Open the app with DATABASE_URL from {STATE / 'demo.json'}.")
        return
    say("opening H-logsen (close the window to stop the app; MySQL keeps running)")
    mode = "--browser" if args.browser else "--desktop"
    environment = {**os.environ, "DATABASE_URL": url(state)}
    environment.pop("FLASK_SECRET_KEY", None)  # a new secret per launch: closing the app signs out
    raise SystemExit(
        subprocess.run([sys.executable, "-m", "app.workbench", mode], env=environment).returncode
    )


if __name__ == "__main__":
    main()
