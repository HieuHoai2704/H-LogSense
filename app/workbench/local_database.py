"""Find the local demonstration database so the desktop app works from its launcher icon.

``python -m scripts.run.demo`` keeps the demo MySQL passwords owner-only in ``.local/demo/demo.json`` of a
source checkout. When the app starts without ``DATABASE_URL``, it looks for that file, starts the demo
container if it is stopped, waits until MySQL answers and then uses the demo database. Nothing happens
in an installed build without a checkout, or when the file is not private to this user.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import time

CONTAINER = "hlogsen-demo-mysql"
PORT = 3308
SCHEMA = "logsense_demo"
STATE = Path(__file__).resolve().parents[2] / ".local" / "demo" / "demo.json"
READY_SECONDS = 90


def demo_url(state, role="app"):
    from sqlalchemy.engine import URL

    user, password = (
        ("root", state["root_password"]) if role == "admin" else ("logsense_app", state["app_password"])
    )
    return URL.create(
        "mysql+pymysql", username=user, password=password, host="127.0.0.1", port=PORT, database=SCHEMA
    ).render_as_string(hide_password=False)


def load_state(path=STATE):
    from app.permissions import check_private

    try:
        if not path.is_file() or not check_private(path):
            return None
        state = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or not all(
        isinstance(state.get(k), str) for k in ("root_password", "app_password")
    ):
        return None
    return state


def reachable(state, timeout=2):
    import pymysql

    try:
        pymysql.connect(
            host="127.0.0.1",
            port=PORT,
            user="logsense_app",
            password=state["app_password"],
            database=SCHEMA,
            connect_timeout=timeout,
        ).close()
        return True
    except pymysql.MySQLError:
        return False


def start_container():
    """Start the stopped demo container; False when Docker is missing or the container does not exist."""
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        running = subprocess.run(
            [docker, "inspect", "-f", "{{.State.Running}}", CONTAINER],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if running.returncode:
            return False
        if running.stdout.strip() != "true":
            started = subprocess.run([docker, "start", CONTAINER], capture_output=True, timeout=60)
            return started.returncode == 0
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def use_demo_database(path=STATE, wait=READY_SECONDS):
    """Set DATABASE_URL to the demo database when none is configured. Returns True when it did."""
    if os.environ.get("DATABASE_URL"):
        return False
    state = load_state(path)
    if state is None:
        return False
    if not reachable(state):
        if not start_container():
            return False
        deadline = time.monotonic() + wait
        while not reachable(state):
            if time.monotonic() > deadline:
                return False
            time.sleep(1.5)
    os.environ["DATABASE_URL"] = demo_url(state)
    return True
