"""Read-only observation of an existing process in the selected project."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

import psutil

from .files import WorkspaceError, atomic_write, component, project_path, tail

MANIFEST_NAME = "h-logsen.json"
ATTACH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
SAMPLE_PERIOD = 3
MAX_SAMPLES = 120


def process_for(root, pid, created=None):
    if type(pid) is not int or not 1 <= pid <= 2**31 - 1:
        raise WorkspaceError("Invalid PID.")
    process = psutil.Process(pid)
    if created is not None and process.create_time() != created:
        raise psutil.NoSuchProcess(pid)
    if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
        raise psutil.NoSuchProcess(pid)
    if process.username() != psutil.Process().username() or not Path(process.cwd()).resolve().is_relative_to(root):
        raise WorkspaceError("The PID must belong to the current account and run in the project folder.", 403)
    return process


def validated_process(root, pid, created=None):
    try:
        return process_for(root, pid, created)
    except psutil.NoSuchProcess as error:
        raise WorkspaceError("The PID is no longer running or has been reused.", 404) from error
    except (psutil.AccessDenied, OSError) as error:
        raise WorkspaceError("Could not read this process.", 403) from error


def run_id(value):
    if not isinstance(value, str) or not ATTACH_ID.fullmatch(value) or not component(value):
        raise WorkspaceError("run_id needs 1–64 letters, digits, hyphens, dots or underscores.")
    return value


def checked_paths(root, log, metrics):
    paths = {}
    for key, value, suffixes in (("log", log, {".log", ".txt"}), ("metrics", metrics, {".csv"})):
        if value == "":
            paths[key] = ""
            continue
        path = project_path(root, value, missing=True)
        if path.suffix.casefold() not in suffixes or (path.exists() and not path.is_file()):
            raise WorkspaceError("Choose a .log/.txt log and .csv metrics in the project.")
        paths[key] = value
    return paths


def manifest(root, identifier):
    identifier = run_id(identifier)
    path = project_path(root, f"runs/{identifier}/{MANIFEST_NAME}")
    if not path.is_file() or path.stat().st_size > 8192:
        raise WorkspaceError("Invalid run manifest.")
    try:
        with path.open("rb") as stream:
            raw = stream.read(8193)
        data = json.loads(raw)
        if len(raw) > 8192 or not isinstance(data, dict) or type(data["process_created"]) not in (int, float):
            raise ValueError
        paths = checked_paths(root, data.get("log", ""), data.get("metrics", ""))
        process = validated_process(root, data["pid"], data["process_created"])
    except (KeyError, ValueError, RecursionError) as error:
        raise WorkspaceError("Invalid run manifest.") from error
    return process, paths


def status(record, root):
    try:
        process_for(root, record["pid"], record["process_created"])
        return "running"
    except psutil.NoSuchProcess:
        return "ended"
    except (WorkspaceError, psutil.AccessDenied, OSError):
        return "unavailable"


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def sample(folder, record, root, lock):
    """Capture only this PID. Each sample uses the previous measured CPU counters."""
    with lock():
        path = folder / "machine.jsonl"
        try:
            lines = tail(path)["text"].splitlines() if path.is_file() else []
            previous = json.loads(lines[-1]) if lines else {}
        except (ValueError, OSError, WorkspaceError):
            lines, previous = [], {}
        stamp = time.time()
        interval = stamp - previous.get("_sampled_at", 0)
        if 0 <= interval < SAMPLE_PERIOD:
            return
        try:
            process = process_for(root, record["pid"], record["process_created"])
            cpu = process.cpu_times()
            used = process.memory_info().rss
        except (WorkspaceError, psutil.Error, OSError):
            return
        total = psutil.virtual_memory().total
        cpu_total = cpu.user + cpu.system
        previous_cpu = previous.get("_cpu_seconds")
        percent = None
        if interval > 0 and previous_cpu is not None and cpu_total >= previous_cpu:
            percent = min(100, 100 * (cpu_total - previous_cpu) / interval / (os.cpu_count() or 1))
        data = {"timestamp": timestamp(stamp), "cpu_percent": percent, "ram_percent": used / total * 100 if total else None,
                "ram_used_bytes": used, "ram_total_bytes": total, "_sampled_at": stamp, "_cpu_seconds": cpu_total}
        atomic_write(path, ("\n".join([*lines[-(MAX_SAMPLES - 1):], json.dumps(data)]) + "\n").encode("utf-8"))


def register(root, identifier, pid, log, metrics):
    root = root.resolve(strict=True)
    identifier = run_id(identifier)
    process = validated_process(root, pid)
    paths = checked_paths(root, log, metrics)
    runs = project_path(root, "runs", missing=True)
    runs.mkdir(exist_ok=True)
    directory = project_path(root, "runs/" + identifier, missing=True)
    directory.mkdir(exist_ok=True)
    path = project_path(root, f"runs/{identifier}/{MANIFEST_NAME}", missing=True)
    record = {"pid": process.pid, "process_created": process.create_time(), **paths}
    atomic_write(path, json.dumps(record, ensure_ascii=False).encode("utf-8"))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--log", default="")
    parser.add_argument("--metrics", default="")
    args = parser.parse_args()
    try:
        print(register(args.root, args.run_id, args.pid, args.log, args.metrics))
    except (OSError, WorkspaceError, psutil.Error) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
