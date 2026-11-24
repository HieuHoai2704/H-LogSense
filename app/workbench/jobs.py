"""Local interpreter, telemetry, and independent training runs."""

from collections import deque
import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import psutil

from . import attached, run_profile
from .files import WorkspaceError, atomic_write, linked, tail
from .terminal import child_environment

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RUN_LIMIT = 2


def now():
    return datetime.now(timezone.utc).isoformat()


def interpreters(root):
    executable = Path(sys.executable)
    if os.name == "nt" and executable.name.casefold() == "pythonw.exe":
        console = executable.with_name("python.exe")
        if console.is_file():
            executable = console
    candidates = {"app": executable}
    for name in (".venv", "venv"):
        environment = root / name
        executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if (environment / "pyvenv.cfg").is_file() and executable.is_file() and not linked(environment):
            candidates[name] = executable
    return candidates


def runtime_id(store, root, available):
    identifier = store.state["interpreters"].get(str(root))
    if identifier in available:
        return identifier
    return next(name for name in (".venv", "venv", "app") if name in available)


def package_list(executable, root):
    snippet = (
        "import importlib.metadata as m, json, sys;"
        "print(json.dumps({'version':sys.version.split()[0],"
        "'packages':sorted([[d.metadata.get('Name') or '',d.version] for d in m.distributions()])[:1000]}))"
    )
    try:
        output = subprocess.run([str(executable), "-I", "-c", snippet], cwd=root, env=child_environment(),
                                capture_output=True, text=True, timeout=8, check=True, creationflags=NO_WINDOW)
        return json.loads(output.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise WorkspaceError("Không đọc được môi trường Python đã chọn.", 422) from None


def sample_machine(include_gpu):
    ram = psutil.virtual_memory()
    sample = {"timestamp": now(), "cpu_percent": psutil.cpu_percent(interval=0.1), "ram_percent": ram.percent,
              "ram_used_bytes": ram.total - ram.available, "ram_total_bytes": ram.total, "gpu": []}
    executable = shutil.which("nvidia-smi") if include_gpu else None
    if executable:
        try:
            output = subprocess.run(
                [executable, "--query-gpu=index,name,uuid,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2, check=True, creationflags=NO_WINDOW,
            )
            for row in csv.reader(output.stdout.splitlines(), skipinitialspace=True):
                if len(row) != 6 or not row[0].strip().isdecimal():
                    continue
                index, name, uuid, gpu, used, total = row
                sample["gpu"].append({"index": int(index), "name": name.strip(), "uuid": uuid.strip(),
                                      "percent": number(gpu), "vram_used_mib": number(used), "vram_total_mib": number(total)})
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return sample


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def utc_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if timestamp.utcoffset() is not None:
            return timestamp.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError):
        pass
    return None


def training_metrics(text):
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames or "epoch" not in reader.fieldnames or not {"train_loss", "val_loss"} & set(reader.fieldnames):
        raise WorkspaceError("metrics.csv cần cột epoch và train_loss hoặc val_loss.", 422)
    rows = deque(maxlen=120)
    for row in reader:
        epoch, training, validation = (number(row.get(key)) for key in ("epoch", "train_loss", "val_loss"))
        if epoch is not None and (training is not None or validation is not None):
            point = {"epoch": epoch, "train_loss": training, "val_loss": validation}
            timestamp = utc_timestamp(row.get("timestamp"))
            if timestamp is not None:
                point["timestamp"] = timestamp
            rows.append(point)
    return list(rows)


def machine_metrics(text):
    rows = deque(maxlen=120)
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(row, dict):
            continue
        stamp = utc_timestamp(row.get("timestamp"))
        if stamp is None:
            continue
        result = {key: number(row.get(key)) for key in ("cpu_percent", "gpu_percent", "ram_percent",
                                                        "ram_used_bytes", "ram_total_bytes",
                                                        "vram_used_mib", "vram_total_mib")}
        devices = row.get("gpu")
        result["gpu"] = []
        if isinstance(devices, list):
            for position, device in enumerate(devices[:32]):
                if not isinstance(device, dict):
                    continue
                index = device.get("index", position)
                if type(index) is not int or not 0 <= index <= 255:
                    continue
                identifiers = {key: device[key].strip()[:160] for key in ("name", "uuid") if isinstance(device.get(key), str)}
                readings = {key: number(device.get(key)) for key in ("percent", "vram_used_mib", "vram_total_mib")}
                result["gpu"].append({"index": index, **identifiers, **readings})
        if result["gpu"]:
            for field, key in (("gpu_percent", "percent"), ("vram_used_mib", "vram_used_mib"), ("vram_total_mib", "vram_total_mib")):
                result[field] = result["gpu"][0][key]
        rows.append({"timestamp": stamp, **result})
    return list(rows)


class Runs:
    def __init__(self, store):
        self.store = store
        self.directory = store.directory / "runs"
        self.directory.mkdir(exist_ok=True, mode=0o700)

    def path(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise WorkspaceError("Mã lượt chạy không hợp lệ.")
        folder = self.directory / run_id
        if not folder.is_dir() or linked(folder):
            raise WorkspaceError("Không tìm thấy lượt chạy.", 404)
        return folder

    def get(self, run_id, root):
        folder = self.path(run_id)
        record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        if record["root"] != str(root):
            raise WorkspaceError("Không tìm thấy lượt chạy trong dự án này.", 404)
        if record.get("source") == "attached":
            record["status"] = attached.status(record, root)
        elif record["status"] in {"starting", "running"} and not running(record):
            record["status"] = "interrupted"
        return record

    def recent(self, root):
        rows = []
        for folder in sorted(self.directory.iterdir(), key=lambda item: item.stat().st_mtime_ns, reverse=True)[:100]:
            try:
                rows.append(self.get(folder.name, root))
            except (OSError, ValueError, WorkspaceError):
                continue
            if len(rows) >= 30:
                break
        return rows

    def start(self, run_id, root, script, args, config_files):
        choices = interpreters(root)
        identifier = runtime_id(self.store, root, choices)
        interpreter = choices[identifier]
        file = self.store.resolve(script, root=root)
        if file.suffix.casefold() != ".py" or not file.is_file():
            raise WorkspaceError("Chọn một tệp Python trong dự án.")
        if (not isinstance(args, list) or len(args) > 40
                or any(not isinstance(item, str) or len(item) > 1024 or "\0" in item for item in args)):
            raise WorkspaceError("Tham số chạy không hợp lệ.")
        if not isinstance(config_files, list) or len(config_files) > 8:
            raise WorkspaceError("Chọn tối đa tám tệp cấu hình trong dự án.")
        for name in config_files:
            path = self.store.resolve(name, root=root)
            if path.suffix.casefold() not in run_profile.CONFIG_SUFFIXES or not path.is_file():
                raise WorkspaceError("Chọn tệp cấu hình JSON, TOML, YAML, INI, CFG, TXT hoặc lockfile.")
        with self.store.profile_lock():
            if sum(row.get("source") != "attached" and row["status"] in {"starting", "running"}
                   for row in self.recent(root)) >= RUN_LIMIT:
                raise WorkspaceError("Tối đa hai lượt chạy đồng thời cho dự án.", 409)
            folder = self.directory / run_id
            folder.mkdir(mode=0o700)
            (folder / "artifacts").mkdir(mode=0o700)
            record = {"id": run_id, "root": str(root), "script": script, "status": "starting", "started_at": now(),
                      "gpu": self.store.state["features"]["gpu"]}
            save_record(folder, record)
            command = [sys.executable, "-B", "-m", "app.workbench.runner", str(folder), str(interpreter),
                       identifier, json.dumps(config_files), *args]
            options = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                       if os.name == "nt" else {"start_new_session": True})
            try:
                process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2], env=child_environment(),
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           **options)
            except OSError:
                save_record(folder, {**record, "status": "failed", "ended_at": now()})
                raise WorkspaceError("Không khởi động được bộ theo dõi.", 503) from None
            from threading import Thread
            Thread(target=process.wait, daemon=True).start()
            return record

    def attach(self, root, values):
        reference = values.get("run_id")
        pid = values.get("pid")
        if (reference is None) == (pid is None):
            raise WorkspaceError("Chọn PID hoặc run_id.")
        if reference is not None:
            reference = attached.run_id(reference)
            if re.fullmatch(r"[0-9a-f]{32}", reference) and (self.directory / reference).exists():
                return self.get(reference, root)
            process, paths = attached.manifest(root, reference)
        else:
            process = attached.validated_process(root, pid)
            paths = attached.checked_paths(root, values.get("log", ""), values.get("metrics", ""))
        created = process.create_time()
        key = json.dumps([str(root), process.pid, created])
        identifier = sha256(key.encode("utf-8")).hexdigest()[:32]
        with self.store.profile_lock():
            folder = self.directory / identifier
            folder.mkdir(mode=0o700, exist_ok=True)
            folder = self.path(identifier)
            existing = folder / "run.json"
            if existing.is_file():
                previous = self.get(identifier, root)
                if previous.get("source") != "attached":
                    raise WorkspaceError("run_id đã được sử dụng.", 409)
                reference = reference or previous.get("external_id")
            record = {"id": identifier, "root": str(root), "source": "attached", "pid": process.pid,
                      "process_created": created, "status": "running", "started_at": attached.timestamp(created),
                      "external_id": reference, "script": reference or f"PID {process.pid}", **paths}
            save_record(folder, record)
        return record

    def stop(self, run_id, root):
        record = self.get(run_id, root)
        if record.get("source") == "attached":
            raise WorkspaceError("Lượt chạy gắn ngoài chỉ được theo dõi.", 403)
        if record["status"] not in {"starting", "running"}:
            raise WorkspaceError("Lượt chạy đã kết thúc.", 409)
        (self.path(run_id) / "stop.requested").touch()

    def profile(self, run_id, root):
        return run_profile.read(self.path(run_id), self.get(run_id, root))

    def output(self, run_id, root, offset, stamp):
        record = self.get(run_id, root)
        folder = self.path(run_id)
        if record.get("source") == "attached":
            if record["status"] == "running":
                attached.sample(folder, record, root, self.store.profile_lock)
            log_path = self.external_file(root, record["log"])
            log = tail(log_path, offset, stamp) if log_path else {
                "changed": offset != 0 or stamp != "", "text": "", "offset": 0, "stamp": ""}
            samples, training = self.measurements(folder, self.external_file(root, record["metrics"]), external=True)
            return {"run": record, "log": log, "machine": samples, "training": training}
        path = folder / "train.log"
        log = tail(path, offset, stamp) if path.is_file() else {"changed": True, "text": "", "offset": 0, "stamp": ""}
        samples, training = self.measurements(folder)
        return {"run": record, "log": log, "machine": samples, "training": training}

    def compare(self, left, right, root):
        if left == right:
            raise WorkspaceError("Chọn hai lượt chạy khác nhau.")
        runs = [self.get(identifier, root) for identifier in (left, right)]
        if any(record.get("source") == "attached" for record in runs):
            raise WorkspaceError("So sánh hiện dùng các lượt do H-logsen khởi chạy.")
        compared = []
        for record in runs:
            folder = self.path(record["id"])
            samples, training = self.measurements(folder)
            snapshot = run_profile.load_snapshot(folder, record["id"])
            machine = {}
            for field in ("cpu_percent", "gpu_percent", "ram_percent", "vram_used_mib"):
                values = [row[field] for row in samples if row[field] is not None and row[field] >= 0
                          and (field == "vram_used_mib" or row[field] <= 100)]
                machine[field] = {"samples": len(values), "peak": max(values, default=None)}
            compared.append({
                "run": {key: record.get(key) for key in ("id", "script", "status", "started_at", "ended_at", "exit_code", "source", "pid")},
                "profile": snapshot, "training": training, "machine": machine
            })
        return {"runs": compared}

    def external_file(self, root, name):
        if name:
            try:
                path = self.store.resolve(name, root=root)
                if path.is_file():
                    return path
            except (OSError, WorkspaceError):
                pass
        return None

    @staticmethod
    def measurements(folder, metrics=None, *, external=False):
        machine = folder / "machine.jsonl"
        samples = machine_metrics(tail(machine)["text"]) if machine.is_file() and not linked(machine) else []
        if not external:
            metrics = folder / "metrics.csv"
        if metrics is not None and metrics.is_file() and not linked(metrics):
            try:
                with metrics.open("rb") as stream:
                    data = stream.read(1024 * 1024 + 1)
                training = training_metrics(data.decode("utf-8-sig")) if len(data) <= 1024 * 1024 else []
            except (OSError, ValueError, csv.Error, WorkspaceError):
                training = []
        else:
            training = []
        return samples, training


def running(record):
    pid = record.get("runner_pid")
    if not pid:
        return record["status"] == "starting" and (
            datetime.now(timezone.utc) - datetime.fromisoformat(record["started_at"])
        ).total_seconds() < 15
    try:
        return psutil.Process(pid).create_time() == record["runner_created"]
    except psutil.Error:
        return False


def terminate_run(process):
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    process.terminate()
    _, alive = psutil.wait_procs(descendants, timeout=1)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def save_record(folder, record):
    atomic_write(folder / "run.json", json.dumps(record, ensure_ascii=False).encode("utf-8"))


def execute_run(folder, interpreter, identifier, config_files, args):
    """Executed by a detached supervisor so browser/Flask restarts preserve the job."""
    record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    root = Path(record["root"])
    script = root / record["script"]
    record.update(runner_pid=os.getpid(), runner_created=psutil.Process().create_time())
    save_record(folder, record)
    process = None
    try:
        env = {**child_environment(), "H_LOGSEN_RUN_ID": record["id"],
               "H_LOGSEN_METRICS_CSV": str(folder / "metrics.csv"),
               "H_LOGSEN_ARTIFACTS_DIR": str(folder / "artifacts"), "PYTHONIOENCODING": "utf-8"}
        with (folder / "train.log").open("xb") as log, (folder / "machine.jsonl").open("x", encoding="utf-8") as metrics:
            if script.resolve(strict=True) != script or not script.is_file():
                raise OSError("Script path changed")
            try:
                run_profile.capture(folder, record, interpreter, identifier, config_files, args)
            except OSError:
                # Provenance is supplemental. A snapshot failure should not stop the run.
                pass
            if (folder / "stop.requested").exists():
                record.update(status="stopped")
                return
            process = subprocess.Popen(
                [interpreter, "-u", str(script), *args], cwd=root, env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
            )
            record.update(status="running", pid=process.pid)
            save_record(folder, record)
            while True:
                metrics.write(json.dumps(sample_machine(record["gpu"])) + "\n")
                metrics.flush()
                if (folder / "stop.requested").exists() and process.poll() is None:
                    terminate_run(process)
                    record.update(status="stopped", exit_code=process.returncode)
                    break
                try:
                    result = process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    continue
                record.update(status="completed" if result == 0 else "failed", exit_code=result)
                break
    except (OSError, ValueError, psutil.Error, subprocess.SubprocessError):
        record.update(status="failed")
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    finally:
        save_record(folder, {**record, "ended_at": now()})
