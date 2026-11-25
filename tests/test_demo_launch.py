"""The demo command starts the job worker next to the app and stops it with the app (no Docker here)."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from scripts.run import demo


class DemoLaunchTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        state = patch.object(demo, "STATE", Path(folder.name))
        state.start()
        self.addCleanup(state.stop)

    def launch(self, *, running=None, app=None):
        worker = MagicMock()
        with (
            patch("app.workbench.__main__.running_instance", return_value=running),
            patch.object(demo.subprocess, "Popen", return_value=worker) as popen,
            patch.object(demo.subprocess, "run", side_effect=app or [MagicMock(returncode=0)]) as run,
        ):
            code = demo.launch({"DATABASE_URL": "mysql+pymysql://demo"})
        return code, popen, run, worker

    def test_worker_runs_while_the_app_runs_and_stops_with_it(self):
        code, popen, run, worker = self.launch()
        self.assertEqual(code, 0)
        self.assertEqual(popen.call_args.args[0][1:], ["-m", "scripts.run.worker"])
        self.assertEqual(popen.call_args.kwargs["env"], {"DATABASE_URL": "mysql+pymysql://demo"})
        self.assertEqual(run.call_args.args[0][1:], ["-m", "app.workbench"])
        worker.terminate.assert_called_once()
        worker.wait.assert_called_once()

    def test_ctrl_c_still_stops_the_worker(self):
        code, _popen, _run, worker = self.launch(app=KeyboardInterrupt())
        self.assertEqual(code, 0)
        worker.terminate.assert_called_once()

    def test_a_second_launch_only_reopens_the_browser(self):
        code, popen, run, _worker = self.launch(running="http://127.0.0.1:1/#workbench=token")
        self.assertEqual(code, 0)
        popen.assert_not_called()
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
