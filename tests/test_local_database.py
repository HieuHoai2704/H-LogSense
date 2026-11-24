"""Finding the local demo database when the app starts from its launcher (no real database needed)."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.workbench import local_database


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
