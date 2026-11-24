"""Local workbench security and bounded file, log and run behavior."""

from collections import deque
from hashlib import sha256
import json
from pathlib import Path
from shutil import which
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock
import time
import unittest
from unittest.mock import patch

from app import create_app
from app.workbench import external, jobs, run_profile, tabular
from app.workbench.api import mount
from app.workbench.files import ProjectStore
from app.workbench.terminal import Session, ssh_command

PREFIX = "/api/local/v1"


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.project = self.folder / "project"
        self.project.mkdir()
        app = create_app({"TESTING": True})
        local = mount(app, "test-key", self.folder / "workbench", port=8760)
        self.addCleanup(local["terminals"].shutdown)
        self.client = app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}
        self.origin = "http://127.0.0.1:8760"
        self.select(self.project)

    def call(self, path, method="GET", **kwargs):
        return self.client.open(
            PREFIX + path, method=method, base_url=self.origin, headers=self.headers, **kwargs
        )

    def select(self, root):
        response = self.call("/project", "POST", json={"path": str(root)})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.headers["X-Project"] = response.json["project"]

    def test_public_flask_has_no_local_api_and_workbench_requires_capability_and_host(self):
        standard = create_app({"TESTING": True}).test_client()
        self.assertEqual(standard.get(PREFIX + "/session").status_code, 404)
        self.assertEqual(self.client.get(PREFIX + "/session", base_url=self.origin).status_code, 403)
        for base, headers in (
            ("http://wrong.example:8760", self.headers),
            (self.origin, {**self.headers, "Origin": "http://wrong.example"}),
            (self.origin, {**self.headers, "Sec-Fetch-Site": "cross-site"}),
        ):
            response = self.client.get(PREFIX + "/session", base_url=base, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.call("/session").headers["Cache-Control"], "no-store")
        self.assertIn(str(self.project), self.call("/session").json["recent"])

    def test_code_tools_require_code_scope_and_saved_revision(self):
        script = self.project / "demo.py"
        script.write_text("print(42)\n", encoding="utf-8")
        revision = sha256(script.read_bytes()).hexdigest()
        args = {"path": "demo.py", "revision": revision}
        self.assertEqual(self.call("/code/check", "POST", json=args).status_code, 403)
        self.headers["X-Workspace"] = "code"
        self.select(self.project)
        for route in ("/code/check", "/code/format"):
            self.assertEqual(self.call(route, "POST", json={**args, "revision": "stale"}).status_code, 409)
            self.assertEqual(self.call(route, "POST", json={**args, "path": "../demo.py"}).status_code, 403)
        self.assertEqual(self.call("/code/format", "POST", json={**args, "text": None}).status_code, 400)
        run = self.call("/terminals", "POST", json={"shell": "Run File", **args, "revision": "stale"})
        self.assertEqual(run.status_code, 409)
        self.assertEqual(script.read_text(encoding="utf-8"), "print(42)\n")

    def test_project_file_revision_persistence_and_cross_project_guard(self):
        file = self.project / "train.py"
        file.write_bytes(b"\xef\xbb\xbfprint(1)\r\n")
        self.assertEqual(self.call("/tree").json["entries"], [{"name": "train.py", "directory": False}])
        revision = self.call("/file?path=train.py").json["revision"]
        saved = self.call(
            "/file", "PUT", json={"path": "train.py", "text": "print(2)\n", "revision": revision}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(file.read_bytes(), b"\xef\xbb\xbfprint(2)\r\n")
        stale = self.call("/file", "PUT", json={"path": "train.py", "text": "print(3)", "revision": revision})
        self.assertEqual(stale.status_code, 409)
        outside = self.folder / "other"
        outside.mkdir()
        previous = self.headers["X-Project"]
        self.select(outside)
        self.headers["X-Project"] = previous
        self.assertEqual(self.call("/file?path=train.py").status_code, 409)
        app = create_app({"TESTING": True})
        local = mount(app, "second-key", self.folder / "workbench")
        self.assertEqual(local["store"].root(), outside)

    def test_workspaces_remember_independent_roots_and_reject_cross_scope_project_ids(self):
        code = self.folder / "code"
        analysis = self.folder / "analysis"
        code.mkdir()
        analysis.mkdir()
        for folder, text in ((self.project, "project"), (code, "code"), (analysis, "analysis")):
            (folder / "same.txt").write_text(text, encoding="utf-8")
        project_id = self.headers["X-Project"]
        for workspace, folder in (("code", code), ("analysis", analysis)):
            self.headers["X-Workspace"] = workspace
            result = self.call("/project", "POST", json={"path": str(folder)})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.call("/file?path=same.txt").status_code, 409)
            self.headers["X-Project"] = result.json["project"]
            self.assertEqual(self.call("/file?path=same.txt").json["text"], workspace)
            self.assertEqual(self.call("/session").json["recent"][0], str(folder))
            self.headers["X-Project"] = project_id
        self.headers.pop("X-Workspace")
        self.assertEqual(self.call("/file?path=same.txt").json["text"], "project")
        store = ProjectStore(self.folder / "workbench")
        self.assertEqual(store.workspace_root("project"), self.project)
        self.assertEqual(store.workspace_root("code"), code)
        self.assertEqual(store.workspace_root("analysis"), analysis)
        self.headers["X-Workspace"] = "arbitrary"
        self.assertEqual(self.call("/session").status_code, 400)

    def test_view_state_is_persistent_and_only_accepts_scoped_relative_paths(self):
        payload = {
            "expanded": ["src", "src/nested"],
            "selected": "src/nested/train.log",
            "log": "src/nested/train.log",
        }
        self.assertEqual(self.call("/view-state", "PUT", json=payload).json, payload)
        self.assertEqual(self.call("/view-state", "PUT", json={"log": "../private.log"}).status_code, 400)
        self.assertEqual(
            self.call("/view-state", "PUT", json={"analysis_file": "results.csv"}).status_code, 400
        )
        project_id = self.headers["X-Project"]
        self.headers["X-Workspace"] = "code"
        self.assertEqual(self.call("/view-state").json, {})
        layout = {"left": "main.py", "right": "notes.pdf", "split": True, "active": "right", "ratio": 55}
        self.assertEqual(self.call("/view-state", "PUT", json={"editor": layout}).json["editor"], layout)
        store = ProjectStore(self.folder / "workbench")
        self.assertEqual(store.workspace_view("project", project_id), payload)
        self.assertEqual(store.workspace_view("code", project_id), {"editor": layout})
        self.headers["X-Project"] = "stale"
        self.assertEqual(self.call("/view-state").status_code, 409)

    def test_profile_writers_reload_and_merge_across_separate_processes(self):
        directory = self.folder / "workbench"
        first = ProjectStore(directory)
        code = self.folder / "code"
        analysis = self.folder / "analysis"
        code.mkdir()
        analysis.mkdir()
        script = (
            "import sys,time; from pathlib import Path; from app.workbench.files import ProjectStore\n"
            "store=ProjectStore(sys.argv[1]); Path(sys.argv[3]).touch(); "
            "deadline=time.monotonic()+10\n"
            "while not Path(sys.argv[4]).exists() and time.monotonic()<deadline: time.sleep(.02)\n"
            "store.select(sys.argv[2], 'analysis')\n"
        )
        ready = self.folder / "ready"
        commit = self.folder / "commit"
        with subprocess.Popen(
            [sys.executable, "-c", script, str(directory), str(analysis), str(ready), str(commit)]
        ) as child:
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                first.select(str(code), "code")
                first.save_workspace_view("project", self.headers["X-Project"], {"selected": "train.py"})
                commit.touch()
                self.assertEqual(child.wait(timeout=15), 0)
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
        self.assertEqual(first.workspace_root("code"), code)
        self.assertEqual(first.workspace_root("analysis"), analysis)
        self.assertEqual(first.workspace_view("project", self.headers["X-Project"]), {"selected": "train.py"})

    def test_attach_real_existing_process_reads_its_log_loss_and_process_memory(self):
        from app.workbench import attached

        (self.project / "train.log").write_text(
            "2026-11-08T02:00:00Z INFO original train\n", encoding="utf-8"
        )
        (self.project / "metrics.csv").write_text(
            "epoch,train_loss,timestamp\n1,0.5,2026-11-08T02:00:00Z\n", encoding="utf-8"
        )
        command = [sys.executable, "-c", "import time; time.sleep(30)"]
        with subprocess.Popen(command, cwd=self.project) as process:
            try:
                with subprocess.Popen(command, cwd=self.folder) as other:
                    try:
                        self.assertEqual(
                            self.call("/runs/attach", "POST", json={"pid": other.pid}).status_code, 403
                        )
                    finally:
                        other.terminate()
                self.assertEqual(
                    self.call(
                        "/runs/attach", "POST", json={"pid": process.pid, "log": "../secret.log"}
                    ).status_code,
                    403,
                )
                response = self.call(
                    "/runs/attach",
                    "POST",
                    json={"pid": process.pid, "log": "train.log", "metrics": "metrics.csv"},
                )
                self.assertEqual(response.status_code, 200, response.get_json())
                record = response.json
                self.assertEqual((record["source"], record["pid"]), ("attached", process.pid))
                route = "/runs/" + record["id"]
                output = self.call(route).json
                self.assertIn("original train", output["log"]["text"])
                self.assertEqual(output["training"][0]["train_loss"], 0.5)
                self.assertGreater(output["machine"][0]["ram_used_bytes"], 0)
                self.assertIsNone(output["machine"][0]["cpu_percent"])
                self.assertIsNone(output["machine"][0]["gpu_percent"])
                with patch.object(attached, "SAMPLE_PERIOD", 0):
                    self.assertIsNotNone(self.call(route).json["machine"][-1]["cpu_percent"])
                self.assertEqual(self.call(route + "/stop", "POST").status_code, 403)
                self.assertIsNone(process.poll())
                manifest = attached.register(
                    self.project, "known-run", process.pid, "train.log", "metrics.csv"
                )
                self.assertEqual(
                    self.call("/runs/attach", "POST", json={"run_id": "known-run"}).json["id"], record["id"]
                )
                self.assertEqual(
                    self.call("/runs/attach", "POST", json={"run_id": record["id"]}).json["id"], record["id"]
                )
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                manifest.write_text(
                    json.dumps({**metadata, "process_created": metadata["process_created"] - 1}),
                    encoding="utf-8",
                )
                self.assertEqual(
                    self.call("/runs/attach", "POST", json={"run_id": "known-run"}).status_code, 404
                )
            finally:
                process.terminate()
        self.assertEqual(self.call(route).json["run"]["status"], "ended")
        self.assertIn("original train", self.call(route).json["log"]["text"])

    def test_gpu_sampling_and_recorded_parser_keep_individual_named_devices(self):
        output = (
            "0, First NVIDIA, GPU-a, 5, 512, 4096\nmalformed row\n1, Second NVIDIA, GPU-b, 30, 4096, 8192\n"
        )
        with (
            patch.object(jobs.shutil, "which", return_value="nvidia-smi"),
            patch.object(jobs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output, "")),
        ):
            sample = jobs.sample_machine(True)
        self.assertEqual(
            [(row["uuid"], row["name"], row["percent"]) for row in sample["gpu"]],
            [("GPU-a", "First NVIDIA", 5), ("GPU-b", "Second NVIDIA", 30)],
        )
        parsed = jobs.machine_metrics(json.dumps(sample))[0]
        self.assertEqual(parsed["gpu"], sample["gpu"])
        self.assertEqual(parsed["gpu_percent"], 5)
        self.assertEqual(parsed["gpu"][1]["vram_used_mib"], 4096)

    def test_file_paths_create_rename_and_unsafe_paths(self):
        self.assertEqual(
            self.call("/tree", "POST", json={"action": "directory", "path": "src"}).status_code, 200
        )
        self.assertEqual(
            self.call("/tree", "POST", json={"action": "file", "path": "src/new.py"}).status_code, 200
        )
        self.assertEqual(
            self.call(
                "/tree", "POST", json={"action": "rename", "path": "src/new.py", "target": "src/main.py"}
            ).status_code,
            200,
        )
        self.assertEqual(self.call("/tree?path=src").json["entries"][0]["name"], "main.py")
        (self.project / ".env").write_text("secret", encoding="utf-8")
        for path in ("../outside", ".env", "src/main.py:stream", "CON", "src//main.py"):
            with self.subTest(path=path):
                self.assertEqual(self.call("/file", query_string={"path": path}).status_code, 403)
        self.assertEqual(
            self.call("/tree", "POST", json={"action": "file", "path": "src/main.py"}).status_code, 409
        )
        try:
            (self.project / "symlink").symlink_to(self.folder, target_is_directory=True)
        except OSError:
            pass
        else:
            self.assertEqual(self.call("/tree?path=symlink").status_code, 403)

    def test_pdf_preview_is_bounded_and_project_authorized(self):
        import pypdfium2 as pdf

        name = "report.pdf"
        with pdf.PdfDocument.new() as document:
            document.new_page(240, 300).close()
            document.save(self.project / name)
        query = {"path": name, "page": 1, "zoom": 100}
        response = self.call("/pdf", query_string=query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-PDF-Pages"], "1")
        self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))
        for values in ({"page": 2}, {"zoom": "invalid"}, {"zoom": 500}):
            self.assertEqual(self.call("/pdf", query_string={**query, **values}).status_code, 400)
        self.assertEqual(self.call("/pdf", query_string={**query, "path": "../outside.pdf"}).status_code, 403)
        (self.project / "bad.pdf").write_text("bad PDF")
        self.assertEqual(self.call("/pdf", query_string={**query, "path": "bad.pdf"}).status_code, 422)
        self.headers["X-Project"] = "stale"
        self.assertEqual(self.call("/pdf", query_string=query).status_code, 409)
        self.assertEqual(self.call("/ports").status_code, 409)
        self.assertEqual(
            self.call("/terminals", "POST", json={"shell": "Python Debug", "path": name}).status_code, 409
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows GUI launcher")
    def test_gui_python_uses_console_interpreter_for_project_processes(self):
        console = Path(sys.executable).with_name("python.exe")
        with patch.object(jobs.sys, "executable", str(console.with_name("pythonw.exe"))):
            self.assertEqual(jobs.interpreters(self.project)["app"], console)

    def test_live_log_reads_append_replacement_and_truncation(self):
        path = self.project / "train.log"
        path.write_bytes(b"INFO first\n")
        first = self.call("/log?path=train.log").json
        args = {"path": "train.log", "offset": first["offset"], "stamp": first["stamp"]}
        self.assertFalse(self.call("/log", query_string=args).json["changed"])
        with path.open("ab") as stream:
            stream.write(b"WARN more\n")
        self.assertIn("WARN more", self.call("/log", query_string=args).json["text"])
        path.write_bytes(b"")
        self.assertEqual(self.call("/log", query_string=args).json["text"], "")
        path.write_bytes(b"x" * 100_000)
        self.assertLessEqual(len(self.call("/log?path=train.log").json["text"]), 64 * 1024)

    def test_explorer_search_matches_collapsed_paths_and_respects_limits_and_scope(self):
        cache = self.project / "nested" / "cache_heldout"
        cache.mkdir(parents=True)
        (cache / "Base_s42.npz").write_bytes(b"binary")
        (cache / ".private.npz").write_bytes(b"private")
        outside = self.folder / "outside"
        outside.mkdir()
        (outside / "outside.npz").write_bytes(b"private")
        try:
            (self.project / "linked").symlink_to(outside, target_is_directory=True)
        except OSError:
            pass
        self.assertEqual(
            self.call("/tree/search", query_string={"q": ".NPZ"}).json["entries"],
            [{"name": "Base_s42.npz", "path": "nested/cache_heldout/Base_s42.npz", "directory": False}],
        )
        result = self.call("/tree/search", query_string={"q": "nested\\cache_heldout"}).json
        self.assertTrue(result["entries"][0]["directory"])
        self.assertEqual(self.call("/tree/search").status_code, 400)
        with patch("app.workbench.files.SEARCH_ENTRIES", 1):
            self.assertTrue(self.call("/tree/search", query_string={"q": "missing"}).json["partial"])
        for index in range(3):
            (self.project / f"item-{index}.txt").write_bytes(b"text")
        with patch("app.workbench.files.SEARCH_RESULTS", 2):
            result = self.call("/tree/search", query_string={"q": "item-"}).json
            self.assertEqual(len(result["entries"]), 2)
            self.assertTrue(result["partial"])
        original = self.headers["X-Project"]
        self.select(outside)
        self.headers["X-Project"] = original
        self.assertEqual(self.call("/tree/search", query_string={"q": "npz"}).status_code, 409)

    def test_metrics_discover_only_a_real_local_default_log(self):
        self.assertIsNone(self.call("/metrics").json["default_log"])
        (self.project / "train.log").write_bytes(b"INFO ready\n")
        self.assertEqual(self.call("/metrics").json["default_log"], "train.log")

    def test_metrics_and_external_units_are_separate(self):
        (self.project / "metrics.csv").write_text(
            "epoch,train_loss,val_loss\n1,0.4,0.6\n2,0.2,\n", encoding="utf-8"
        )
        (self.project / "machine.jsonl").write_text(
            '{"timestamp":"2026-11-07T02:00:00Z","cpu_percent":23,"ram_percent":61}\n', encoding="utf-8"
        )
        result = self.call("/metrics").json
        self.assertEqual(result["training"][1]["val_loss"], None)
        self.assertEqual(result["machine"][0]["cpu_percent"], 23)
        report = external.analyze(
            "081109 203615 148 INFO dfs.DataNode: received blk_-123 and blk_456\nbad", "hdfs"
        )
        self.assertEqual((report["events"], report["malformed"], report["distinct_unit_ids"]), (1, 1, 2))
        vm = "2fcbcc11-fbea-4e57-83b4-e21636c35899"
        stack = external.analyze(
            f"nova.log.1 2017-05-16 00:00:04.562 2931 INFO nova.compute [instance: {vm}] Paused\n",
            "openstack",
        )
        self.assertEqual((stack["unit"], stack["distinct_unit_ids"]), ("openstack_instance", 1))
        result = external.evaluate("unit_id,label,prediction\nblk_1,1,1\nblk_2,0,1\n", "hdfs_block")
        self.assertEqual((result["tp"], result["fp"], result["precision"], result["fpr"]), (1, 1, 0.5, 1))
        with self.assertRaises(external.WorkspaceError):
            external.evaluate("unit_id,label,prediction\nblk_1,1,1\nblk_1,0,1\n", "hdfs_block")
        self.assertEqual(
            self.call("/features", "PUT", json={"feature": "external_parsers", "enabled": False}).status_code,
            200,
        )
        self.assertEqual(
            self.call("/external", "POST", json={"path": "metrics.csv", "format": "csv"}).status_code, 403
        )

    def test_child_environment_keeps_nvml_paths_and_filters_credentials(self):
        import os
        from unittest.mock import patch

        from app.workbench.terminal import child_environment

        values = {
            "PROGRAMFILES": "system",
            "PROGRAMW6432": "native-system",
            "DATABASE_URL": "private",
            "FLASK_SECRET_KEY": "private",
        }
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(child_environment(), {"PROGRAMFILES": "system", "PROGRAMW6432": "native-system"})

    def test_local_shell_home_fallback_preserves_project_and_ssh_guards(self):
        shell = next(iter(self.call("/session").json["shells"]), None)
        if not shell:
            self.skipTest("No supported local shell")
        with patch("app.workbench.terminal.Terminals.add", return_value="test-terminal") as spawn:
            endpoint = "/terminals"
            response = self.call(endpoint, "POST", json={"shell": shell})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json["cwd"], str(self.project))
            self.assertEqual(spawn.call_args.args[1], self.project)
            project = self.headers.pop("X-Project")
            response = self.call(endpoint, "POST", json={"shell": shell})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(spawn.call_args.args[1], Path.home())
            self.assertEqual(self.call("/tree").status_code, 409)
            self.assertEqual(self.call(endpoint, "POST", json={"shell": "SSH"}).status_code, 409)
            self.headers["X-Project"] = project + "-stale"
            self.assertEqual(self.call(endpoint, "POST", json={"shell": shell}).status_code, 409)
            self.assertEqual(
                self.client.post(PREFIX + endpoint, base_url=self.origin, json={"shell": shell}).status_code,
                403,
            )
            self.assertEqual(spawn.call_count, 2)

    def test_shell_environment_prefers_selected_python_and_filters_credentials(self):
        import os

        from app.workbench.terminal import terminal_environment

        interpreter = self.project / ".venv" / "bin" / "python"
        interpreter.parent.mkdir(parents=True)
        (interpreter.parent.parent / "pyvenv.cfg").touch()
        with patch.dict(
            os.environ, {"Path": "system-path", "VIRTUAL_ENV": "wrong", "DATABASE_URL": "secret"}, clear=True
        ):
            environment = terminal_environment(interpreter)
            self.assertEqual(environment["PATH"].split(os.pathsep), [str(interpreter.parent), "system-path"])
            self.assertEqual(environment["VIRTUAL_ENV"], str(interpreter.parent.parent))
            self.assertNotIn("DATABASE_URL", environment)

    def test_terminal_wait_rejects_invalid_and_unbounded_values(self):
        for wait_ms in ("bad", "-1", "601"):
            with self.subTest(wait_ms=wait_ms):
                self.assertEqual(
                    self.call("/terminals/missing", query_string={"wait_ms": wait_ms}).status_code, 400
                )
        self.assertEqual(self.call("/terminals/missing", query_string={"wait_ms": 500}).status_code, 404)

    def test_training_metric_time_accepts_offsets_and_leaves_untimed_rows_available(self):
        points = jobs.training_metrics(
            "epoch,train_loss,val_loss,timestamp\n"
            "1,0.4,0.5,2026-11-07T10:00:00.123+07:00\n"
            "2,0.2,,2026-11-07T03:01:00\n"
            "3,0.1,,2026-02-30T03:02:00Z\n"
        )
        self.assertEqual(points[0]["timestamp"], "2026-11-07T03:00:00.123Z")
        self.assertNotIn("timestamp", points[1])
        self.assertNotIn("timestamp", points[2])
        self.assertEqual([point["train_loss"] for point in points], [0.4, 0.2, 0.1])

    def test_terminal_cursor_returns_only_unread_output_and_reports_buffer_gaps(self):
        session = Session.__new__(Session)
        session.lock = Lock()
        session.buffer = deque(["ab", "đc"])
        session.length = 4
        session.offset = 10
        session.finished = session.closed = False
        self.assertEqual(
            session.snapshot(8),
            {"text": "đc", "start_offset": 8, "offset": 10, "reset": False, "finished": False},
        )
        lost = session.snapshot(3)
        self.assertTrue(lost["reset"])
        self.assertEqual((lost["start_offset"], lost["text"]), (6, "abđc"))
        self.assertEqual(session.snapshot(lost["offset"])["text"], "")
        self.assertTrue(session.snapshot(11)["reset"])

    def test_ssh_rejects_options_and_pins_known_host_policy(self):
        with self.assertRaises(external.WorkspaceError):
            ssh_command("-oProxyCommand=oops", "operator", 22)
        from shutil import which

        if which("ssh"):
            command = ssh_command("remote.example", "operator", 2222)
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertEqual(command[-2:], ["--", "remote.example"])

    def test_real_background_training_writes_log_and_survives_reopening_store(self):
        path = self.project / "train.py"
        path.write_text(
            "import os\nfrom pathlib import Path\n"
            "print('2026-11-07T03:00:00Z INFO worker-started', flush=True)\n"
            "Path(os.environ['H_LOGSEN_METRICS_CSV']).write_text('epoch,train_loss,val_loss\\n1,0.4,0.5\\n')\n",
            encoding="utf-8",
        )
        with path.open("a", encoding="utf-8") as script:
            script.write(
                "import sys\n"
                "target = Path(os.environ['H_LOGSEN_ARTIFACTS_DIR']) / 'weights.bin'\n"
                "target.write_bytes(os.environ['H_LOGSEN_RUN_ID'].encode())\n"
                "assert 'ARGUMENT_SECRET_TEST' in sys.argv\n"
            )
        config = self.project / "train.yaml"
        config.write_bytes(b"password: CONFIG_SECRET_TEST\n")
        (self.project / "requirements.txt").write_bytes(b"# dependency snapshot input\n")
        response = self.call(
            "/runs",
            "POST",
            json={
                "script": "train.py",
                "config_files": ["train.yaml"],
                "args": ["--epochs", "8", "--token", "ARGUMENT_SECRET_TEST"],
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        run = response.json["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = self.call("/runs/" + run)
            self.assertEqual(result.status_code, 200, result.get_json())
            if result.json["run"]["status"] in ("completed", "failed", "interrupted"):
                break
            time.sleep(0.2)
        self.assertEqual(result.json["run"]["status"], "completed", result.json)
        self.assertIn("worker-started", result.json["log"]["text"])
        self.assertEqual(result.json["training"][0]["train_loss"], 0.4)
        self.assertIsNotNone(result.json["machine"][0]["ram_percent"])
        second = jobs.Runs(ProjectStore(self.folder / "workbench"))
        self.assertEqual(second.get(run, self.project)["status"], "completed")
        endpoint = "/runs/" + run + "/profile"
        profile = self.call(endpoint).json
        self.assertEqual(profile, second.profile(run, self.project))
        self.assertEqual(profile["profile"]["run_id"], run)
        self.assertEqual(profile["profile"]["script"]["sha256"], sha256(path.read_bytes()).hexdigest())
        self.assertEqual(profile["profile"]["interpreter"]["id"], "app")
        self.assertTrue(profile["profile"]["interpreter"]["version"])
        self.assertEqual(profile["profile"]["parameters"], [{"name": "--epochs", "value": "8"}])
        config_metadata, dependency_metadata = profile["profile"]["config_files"]
        self.assertEqual(config_metadata["sha256"], sha256(config.read_bytes()).hexdigest())
        self.assertEqual(dependency_metadata["path"], "requirements.txt")
        self.assertEqual({stream["kind"] for stream in profile["streams"]}, {"log", "machine", "training"})
        self.assertEqual([file["path"] for file in profile["artifacts"]], ["weights.bin"])
        self.assertEqual((Path(profile["artifact_directory"]) / "weights.bin").read_text(), run)
        self.assertNotIn("SECRET_TEST", json.dumps(profile))
        config.write_bytes(b"changed after the run\n")
        self.assertEqual(self.call(endpoint).json["profile"]["config_files"][0], config_metadata)
        self.assertEqual(self.client.get(PREFIX + endpoint, base_url=self.origin).status_code, 403)
        other = self.folder / "other"
        other.mkdir()
        self.select(other)
        self.assertEqual(self.call(endpoint).status_code, 404)

    def test_legacy_run_profile_and_configuration_validation(self):
        runner = jobs.Runs(ProjectStore(self.folder / "workbench"))
        run_id = "9" * 32
        folder = runner.directory / run_id
        folder.mkdir()
        jobs.save_record(
            folder,
            {
                "id": run_id,
                "root": str(self.project),
                "script": "old.py",
                "status": "completed",
                "started_at": jobs.now(),
            },
        )
        (folder / "train.log").write_bytes(b"historic output\n")
        result = self.call("/runs/" + run_id + "/profile")
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json["profile"])
        self.assertEqual(result.json["streams"][0]["path"], "train.log")
        (self.project / "train.py").write_text("pass", encoding="utf-8")
        (self.project / ".env").write_text("private", encoding="utf-8")
        for files, status in (
            ([".env"], 403),
            (["../outside.yaml"], 403),
            (["missing.yaml"], 404),
            (["train.py"], 400),
            (["file.yaml"] * 9, 400),
            ("config.yaml", 400),
        ):
            with self.subTest(files=files):
                result = self.call("/runs", "POST", json={"script": "train.py", "config_files": files})
                self.assertEqual(result.status_code, status)
        self.assertEqual(list(runner.directory.iterdir()), [folder])

    @unittest.skipUnless(which("git"), "Git executable unavailable")
    def test_git_snapshot_reports_actual_commit_and_project_scoped_changes(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.project), *args]).decode().strip()

        git("init", "-b", "workbench-test")
        subproject = self.project / "src"
        subproject.mkdir()
        script = subproject / "train.py"
        script.write_bytes(b"print(1)\n")
        git("-c", "core.autocrlf=false", "add", "src/train.py")
        git(
            "-c",
            "user.name=Workbench Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Initial source",
        )
        head = git("rev-parse", "HEAD")
        (self.project / "unrelated.txt").write_bytes(b"outside selected subproject\n")
        clean = run_profile.git_snapshot(subproject)
        self.assertEqual(
            clean, {"status": "available", "branch": "workbench-test", "commit": head, "dirty": False}
        )
        script.write_bytes(b"print(2)\n")
        self.assertTrue(run_profile.git_snapshot(subproject)["dirty"])

    def test_artifact_inventory_limits_and_excludes_links_and_sensitive_paths(self):
        root = self.folder / "artifacts"
        root.mkdir()
        (root / ".env").write_bytes(b"private")
        (root / "secrets.json").write_bytes(b"private")
        try:
            (root / "outside.log").symlink_to(self.project / "outside.log")
        except OSError:
            pass
        for index in range(run_profile.ARTIFACT_LIMIT + 1):
            (root / f"{index}.pt").write_bytes(b"x")
        files, limited = run_profile.artifact_inventory(root)
        self.assertTrue(limited)
        self.assertEqual(len(files), run_profile.ARTIFACT_LIMIT)
        self.assertTrue(all(file["path"].endswith(".pt") and file["bytes"] == 1 for file in files))

    def test_tabular_csv_jsonl_schema_quality_and_scan_bounds(self):
        (self.project / "data.csv").write_bytes(b'value,kind\r\n1,"x,y"\r\n1,"x,y"\r\n2,\r\nwrong-width\r\n')
        report = self.call("/external", "POST", json={"path": "data.csv", "format": "csv"}).json
        self.assertEqual(
            (report["total_rows"], report["valid_rows"], report["duplicate_rows"], report["malformed_rows"]),
            (4, 3, 1, 1),
        )
        self.assertEqual(report["columns"][0]["type"], "number")
        self.assertEqual(sum(report["columns"][0]["distribution"]["counts"]), 3)
        self.assertEqual(report["columns"][1]["missing"], 1)
        self.assertEqual(report["preview"][0], ["1", "x,y"])
        jsonl = tabular.text_profile('{"b":3,"a":"ok"}\n{"a":"ok","b":3}\n{"a":null}\n[]\nbad\n', "jsonl")
        self.assertEqual((jsonl["valid_rows"], jsonl["duplicate_rows"], jsonl["malformed_rows"]), (3, 1, 2))
        self.assertEqual([column["missing"] for column in jsonl["columns"]], [1, 1])
        sampled = tabular.text_profile("value\n" + "1\n" * (tabular.MAX_ROWS + 1), "csv")
        self.assertEqual(sampled["scanned_rows"], tabular.MAX_ROWS)
        self.assertTrue(sampled["sampled"])
        self.assertIsNone(sampled["total_rows"])
        self.assertEqual(tabular.text_profile("empty\n", "csv")["columns"][0]["type"], "unknown")
        self.assertEqual(
            self.call("/external", "POST", json={"path": "../escape.csv", "format": "csv"}).status_code, 403
        )

    def test_parquet_real_file_schema_nulls_and_invalid_input(self):
        try:
            import pyarrow as arrow
            import pyarrow.parquet as parquet
        except ImportError:
            self.skipTest("Install pyarrow for Parquet")
        path = self.project / "metrics.parquet"
        parquet.write_table(
            arrow.table({"epoch": [1, 1, 2], "loss": [0.2, 0.2, None]}), path, row_group_size=2
        )
        report = self.call("/external", "POST", json={"path": path.name, "format": "parquet"})
        self.assertEqual(report.status_code, 200, report.get_json())
        self.assertEqual(report.json["total_rows"], 3)
        self.assertEqual(report.json["duplicate_rows"], 1)
        self.assertEqual(report.json["columns"][1]["type"], "double")
        self.assertEqual(report.json["columns"][1]["missing"], 1)
        with patch.object(tabular, "PARQUET_DECODE_BYTES", 1):
            report = tabular.parquet_profile(path)
            self.assertTrue(report["sampled"])
            self.assertEqual(report["scanned_rows"], 0)
            self.assertEqual(report["total_rows"], 3)
        path.write_bytes(b"invalid")
        self.assertEqual(
            self.call("/external", "POST", json={"path": path.name, "format": "parquet"}).status_code, 422
        )

    def test_run_compare_requires_two_local_runs_and_does_not_return_raw_logs(self):
        runner = jobs.Runs(ProjectStore(self.folder / "workbench"))
        first, second = "1" * 32, "2" * 32
        for identifier, rows in ((first, "1,0.3\n2,0.2\n"), (second, "2,0.1\n")):
            folder = runner.directory / identifier
            folder.mkdir()
            jobs.save_record(
                folder,
                {
                    "id": identifier,
                    "root": str(self.project),
                    "script": "train.py",
                    "status": "completed",
                    "started_at": jobs.now(),
                },
            )
            (folder / "metrics.csv").write_text("epoch,train_loss\n" + rows, encoding="utf-8")
            (folder / "train.log").write_bytes(b"not part of comparison payload")
        (runner.directory / first / "machine.jsonl").write_text(
            '{"timestamp":"2026-11-07T03:00:00Z","cpu_percent":28,"gpu_percent":null}\n', encoding="utf-8"
        )
        result = self.call("/runs/compare", query_string={"left": first, "right": second})
        self.assertEqual(result.status_code, 200, result.get_json())
        a, b = result.json["runs"]
        self.assertEqual(a["training"][1]["train_loss"], 0.2)
        self.assertEqual(a["machine"]["cpu_percent"], {"samples": 1, "peak": 28.0})
        self.assertEqual(b["machine"]["gpu_percent"], {"samples": 0, "peak": None})
        self.assertNotIn("not part of comparison payload", json.dumps(result.json))
        self.assertEqual(
            self.call("/runs/compare", query_string={"left": first, "right": first}).status_code, 400
        )
        other = self.folder / "other"
        other.mkdir()
        self.select(other)
        self.assertEqual(
            self.call("/runs/compare", query_string={"left": first, "right": second}).status_code, 404
        )

    def test_stop_background_training_through_reopened_app(self):
        path = self.project / "slow.py"
        path.write_text("import time\nprint('ready', flush=True)\ntime.sleep(20)\n", encoding="utf-8")
        result = self.call("/runs", "POST", json={"script": "slow.py"})
        self.assertEqual(result.status_code, 201)
        run = result.json["id"]
        new_app = create_app({"TESTING": True})
        mount(new_app, "test-key", self.folder / "workbench", port=8760)
        self.client = new_app.test_client()
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                result = self.call("/runs/" + run)
                if "ready" in result.json["log"].get("text", ""):
                    break
                time.sleep(0.2)
            self.assertEqual(result.json["run"]["status"], "running")
        finally:
            self.assertEqual(self.call("/runs/" + run + "/stop", "POST").status_code, 204)
        while time.monotonic() < deadline:
            result = self.call("/runs/" + run)
            if result.json["run"]["status"] == "stopped":
                break
            time.sleep(0.2)
        self.assertEqual(result.json["run"]["status"], "stopped", result.json)


class ContentSecurityPolicyTest(unittest.TestCase):
    def policy(self, workbench=False):
        app = create_app({"TESTING": True})
        if workbench:
            folder = TemporaryDirectory()
            self.addCleanup(folder.cleanup)
            mount(app, "tok", Path(folder.name), port=8760)
            self.addCleanup(app.extensions["workbench"]["terminals"].shutdown)
        response = app.test_client().get("/?source=demo")
        return response.headers["Content-Security-Policy"]

    def test_eval_is_never_allowed(self):
        for workbench in (False, True):
            with self.subTest(workbench=workbench):
                policy = self.policy(workbench)
                self.assertNotIn("unsafe-eval", policy)
                self.assertIn("object-src 'none'", policy)
