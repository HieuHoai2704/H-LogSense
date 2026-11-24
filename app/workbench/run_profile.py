"""Versioned, bounded provenance for one local Python run."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from tempfile import TemporaryFile

from .files import MAX_TEXT, atomic_write, component, linked
from .terminal import child_environment

PROFILE_VERSION = 1
ARTIFACT_LIMIT = 100
SCAN_LIMIT = 1000
CONFIG_NAMES = (
    "pyproject.toml",
    "requirements.txt",
    "requirements.lock",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "environment.yml",
)
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".txt", ".lock"}
RUN_PARAMETERS = {"--epochs", "--batch-size", "--seed", "--learning-rate", "--lr", "--workers", "--steps"}
STREAMS = {"train.log": "log", "machine.jsonl": "machine", "metrics.csv": "training"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git_snapshot(root):
    executable = shutil.which("git")
    if not executable:
        return {"status": "unavailable"}
    command = [executable, "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root)]

    def run(args, output=subprocess.PIPE):
        try:
            return subprocess.run(
                [*command, *args],
                env=child_environment(),
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=3,
                creationflags=NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    inside = run(["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.returncode or inside.stdout.strip() != b"true":
        return {"status": "unavailable"}
    head = run(["rev-parse", "--verify", "HEAD"])
    branch = run(["symbolic-ref", "--quiet", "--short", "HEAD"])
    with TemporaryFile() as changes:
        status = run(["status", "--porcelain=v1", "--untracked-files=normal", "--", "."], changes)
        changes.seek(0)
        dirty = bool(changes.read(1)) if status is not None and status.returncode == 0 else None
    return {
        "status": "available",
        "commit": head.stdout.decode("ascii").strip() if head is not None and head.returncode == 0 else None,
        "branch": branch.stdout.decode("utf-8", "replace").strip()
        if branch is not None and branch.returncode == 0
        else None,
        "dirty": dirty,
    }


def interpreter_snapshot(executable, identifier, root):
    data = {
        "id": identifier,
        "executable": str(executable),
        "version": None,
        "platform": None,
        "architecture": None,
    }
    code = (
        "import json, platform, sys;"
        "print(json.dumps([platform.python_version(), sys.platform, platform.machine()]))"
    )
    try:
        result = subprocess.run(
            [str(executable), "-I", "-S", "-c", code],
            cwd=root,
            env=child_environment(),
            capture_output=True,
            timeout=4,
            check=True,
            creationflags=NO_WINDOW,
        )
        values = json.loads(result.stdout)
        if isinstance(values, list) and len(values) == 3 and all(isinstance(value, str) for value in values):
            data.update(zip(("version", "platform", "architecture"), values, strict=True))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return data


def fingerprint(root, name):
    path = root / name
    try:
        if path.resolve(strict=True) != path or linked(path) or not path.is_file():
            return {"path": name, "status": "unavailable"}
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > MAX_TEXT:
                return {"path": name, "status": "too_large", "bytes": before.st_size}
            data = stream.read(MAX_TEXT + 1)
            after = os.fstat(stream.fileno())
        current = path.stat()
        if len(data) != before.st_size or any(
            (item.st_size, item.st_mtime_ns, item.st_ino, item.st_dev)
            != (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev)
            for item in (after, current)
        ):
            return {"path": name, "status": "changed"}
        return {"path": name, "status": "available", "bytes": len(data), "sha256": sha256(data).hexdigest()}
    except (OSError, RuntimeError):
        return {"path": name, "status": "unavailable"}


def numeric_parameters(args):
    parameters = []
    for index, arg in enumerate(args):
        if arg == "--":
            break
        flag, separator, value = arg.partition("=")
        if flag not in RUN_PARAMETERS:
            continue
        if not separator:
            value = args[index + 1] if index + 1 < len(args) else ""
        if re.fullmatch(
            r"[+-]?(?:[0-9]{1,12}(?:\.[0-9]{1,12})?|\.[0-9]{1,12})(?:[eE][+-]?[0-9]{1,3})?", value
        ):
            parameters.append({"name": flag, "value": value})
    return parameters


def capture(folder, record, interpreter, identifier, config_files, args):
    root = Path(record["root"])
    files = list(dict.fromkeys([*config_files, *(name for name in CONFIG_NAMES if (root / name).is_file())]))
    data = {
        "version": PROFILE_VERSION,
        "run_id": record["id"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git": git_snapshot(root),
        "interpreter": interpreter_snapshot(interpreter, identifier, root),
        "script": fingerprint(root, record["script"]),
        "config_files": [fingerprint(root, name) for name in files],
        "parameters": numeric_parameters(args),
        "argument_count": len(args),
        "gpu_sampling": record["gpu"],
    }
    atomic_write(folder / "profile.json", json.dumps(data, ensure_ascii=False).encode("utf-8"))


def metadata(path, relative, kind):
    try:
        if linked(path):
            return None
        info = path.stat()
        if stat.S_ISREG(info.st_mode):
            return {
                "path": relative,
                "kind": kind,
                "bytes": info.st_size,
                "modified_at": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
            }
    except (OSError, OverflowError, ValueError):
        pass
    return None


def artifact_root(folder):
    root = folder / "artifacts"
    try:
        if not linked(root) and root.is_dir():
            return root
    except OSError:
        pass
    return None


def artifact_inventory(root):
    """List result metadata only, with finite work even for large directory trees."""
    if root is None:
        return [], False
    stack = [(root, 0)]
    artifacts = []
    scanned = 0
    limited = False
    while stack:
        directory, depth = stack.pop()
        try:
            if linked(directory) or not directory.resolve().is_relative_to(root):
                continue
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > SCAN_LIMIT or len(artifacts) >= ARTIFACT_LIMIT:
                        return sorted(artifacts, key=lambda item: item["path"]), True
                    if not component(entry.name):
                        continue
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        if depth < 7:
                            stack.append((path, depth + 1))
                        else:
                            limited = True
                    elif entry.is_file(follow_symlinks=False):
                        item = metadata(path, path.relative_to(root).as_posix(), "artifact")
                        if item:
                            artifacts.append(item)
        except (OSError, RuntimeError):
            limited = True
    return sorted(artifacts, key=lambda item: item["path"]), limited


def load_snapshot(folder, run_id):
    path = folder / "profile.json"
    if metadata(path, path.name, "profile"):
        try:
            with path.open("rb") as stream:
                data = json.loads(stream.read(64 * 1024))
            if (
                isinstance(data, dict)
                and data.get("version") == PROFILE_VERSION
                and data.get("run_id") == run_id
            ):
                return data
        except (OSError, ValueError, RecursionError):
            pass
    return None


def read(folder, record):
    profile = load_snapshot(folder, record["id"])
    location = artifact_root(folder)
    artifacts, limited = artifact_inventory(location)
    streams = [item for name, kind in STREAMS.items() if (item := metadata(folder / name, name, kind))]
    run = {
        key: record.get(key)
        for key in ("id", "root", "script", "status", "started_at", "ended_at", "exit_code")
    }
    return {
        "run": run,
        "profile": profile,
        "streams": streams,
        "artifacts": artifacts,
        "artifact_directory": str(location) if location is not None else None,
        "artifacts_limited": limited,
    }
