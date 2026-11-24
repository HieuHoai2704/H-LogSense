"""Desktop session behaviour without a window or a database: the quit prompt handshake and finding the
local demo database from the launcher icon."""

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from app.workbench import local_database
from app.workbench.desktop import DesktopBridge


class QuitPromptTests(unittest.TestCase):
    def bridge(self, page_answer):
        bridge = DesktopBridge("secret", store=None, folder_dialog=None)
        window = MagicMock()
        destroyed = threading.Event()
        window.destroy.side_effect = destroyed.set
        window.evaluate_js.return_value = page_answer
        bridge._attach(window)
        return bridge, window, destroyed

    def test_close_button_asks_the_page_and_keeps_the_window(self):
        bridge, window, destroyed = self.bridge(page_answer=True)
        self.assertFalse(bridge.closing())  # cancelled: the page shows its own dialog
        for _ in range(100):
            if window.evaluate_js.called:
                break
            threading.Event().wait(0.01)
        window.evaluate_js.assert_called_once()
        self.assertIn("hlogsenRequestQuit", window.evaluate_js.call_args.args[0])
        self.assertFalse(destroyed.wait(0.2))

    def test_page_without_prompt_closes_as_asked(self):
        bridge, window, destroyed = self.bridge(page_answer=False)
        self.assertFalse(bridge.closing())
        self.assertTrue(destroyed.wait(2))
        self.assertTrue(bridge.closing())  # the real close that destroy() triggers is let through

    def test_quit_needs_the_launch_token(self):
        bridge, window, destroyed = self.bridge(page_answer=True)
        self.assertFalse(bridge.quit("wrong"))
        self.assertFalse(destroyed.wait(0.2))
        self.assertTrue(bridge.quit("secret"))
        self.assertTrue(destroyed.wait(2))
        self.assertTrue(bridge.closing())


class ExitWatchdogTests(unittest.TestCase):
    def test_process_ends_although_a_thread_waits_forever(self):
        import subprocess
        import sys
        import time

        script = (
            "import threading\n"
            "from app.workbench.desktop import exit_when_shutdown_stalls\n"
            "threading.Thread(target=threading.Event().wait).start()  # never finishes, not a daemon\n"
            "exit_when_shutdown_stalls(grace=0.2)\n"
            "print('main done', flush=True)\n"
        )
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "main done"), result.stderr)
        self.assertLess(time.monotonic() - started, 10)


class DesktopRendererSafetyTests(unittest.TestCase):
    def test_no_cross_document_view_transitions(self):
        # WebKitGTK 2.52 (the Linux desktop window) crashes on a form navigation such as signing in when
        # a stylesheet opts into cross-document view transitions. Reproduced and confirmed; keep them out.
        static = Path(__file__).resolve().parents[1] / "app" / "static"
        offenders = [
            str(path.relative_to(static))
            for path in static.rglob("*.css")
            if "@view-transition" in path.read_text("utf-8", errors="ignore")
        ]
        self.assertEqual(offenders, [])


class DemoDatabaseTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.state = Path(folder.name) / "demo.json"
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("DATABASE_URL", None)

    def write(self, data, mode=0o600):
        self.state.write_text(json.dumps(data), "utf-8")
        self.state.chmod(mode)

    def test_configured_url_and_missing_or_public_state_are_left_alone(self):
        os.environ["DATABASE_URL"] = "mysql+pymysql://configured/db"
        self.assertFalse(local_database.use_demo_database(self.state))
        self.assertEqual(os.environ["DATABASE_URL"], "mysql+pymysql://configured/db")
        del os.environ["DATABASE_URL"]
        self.assertFalse(local_database.use_demo_database(self.state))  # no file
        self.write({"root_password": "r", "app_password": "a"}, mode=0o644)
        with patch("app.permissions.check_private", return_value=False):
            self.assertFalse(local_database.use_demo_database(self.state))
        self.write(["not", "an", "object"])
        self.assertFalse(local_database.use_demo_database(self.state))
        self.assertNotIn("DATABASE_URL", os.environ)

    def test_running_demo_database_is_used(self):
        self.write({"root_password": "synthetic-root", "app_password": "synthetic-app"})
        with (
            patch("app.permissions.check_private", return_value=True),
            patch.object(local_database, "reachable", return_value=True),
            patch.object(local_database, "start_container") as start,
        ):
            self.assertTrue(local_database.use_demo_database(self.state))
        start.assert_not_called()
        url = os.environ["DATABASE_URL"]
        self.assertTrue(url.startswith("mysql+pymysql://logsense_app:synthetic-app@127.0.0.1:3308/"))
        self.assertTrue(url.endswith("/logsense_demo"))

    def test_stopped_container_is_started_and_awaited(self):
        self.write({"root_password": "synthetic-root", "app_password": "synthetic-app"})
        answers = iter([False, False, True])
        with (
            patch("app.permissions.check_private", return_value=True),
            patch.object(local_database, "reachable", side_effect=lambda state: next(answers)),
            patch.object(local_database, "start_container", return_value=True) as start,
            patch.object(local_database.time, "sleep"),
        ):
            self.assertTrue(local_database.use_demo_database(self.state))
        start.assert_called_once()

    def test_without_docker_nothing_is_configured(self):
        self.write({"root_password": "synthetic-root", "app_password": "synthetic-app"})
        with (
            patch("app.permissions.check_private", return_value=True),
            patch.object(local_database, "reachable", return_value=False),
            patch.object(local_database.shutil, "which", return_value=None),
        ):
            self.assertFalse(local_database.use_demo_database(self.state))
        self.assertNotIn("DATABASE_URL", os.environ)


if __name__ == "__main__":
    unittest.main()
