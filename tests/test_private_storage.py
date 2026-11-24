"""Workbench root sandbox and owner-only storage (audit batch 2)."""

import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import warnings

from app import create_app
from app.permissions import InsecurePermissions, check_private, open_private, write_private
from app.workbench import files
from app.workbench.api import mount
from app.workbench.files import ProjectStore, WorkspaceError, component, root_allowed

PREFIX = "/api/local/v1"
BASE = "http://127.0.0.1:8760"


class RootSandboxTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name).resolve()
        self.state = self.folder / "state"
        self.project = self.folder / "work" / "project"
        self.project.mkdir(parents=True)
        self.store = ProjectStore(self.state)

    def refused(self, path):
        with self.assertRaises(WorkspaceError, msg=str(path)):
            self.store.select(str(path))

    def test_system_home_temp_and_hidden_roots_are_refused(self):
        hidden = self.folder / "work" / ".secrets"
        hidden.mkdir()
        candidates = [
            Path.home(),
            Path(self.folder.anchor),
            Path(os.path.realpath(__import__("tempfile").gettempdir())),
            hidden,
            self.state,
        ]
        if os.name != "nt":
            candidates += [Path("/etc"), Path("/usr/bin"), Path("/var")]
        for path in candidates:
            if path.is_dir():
                self.refused(path)

    def test_an_ancestor_of_the_profile_store_is_refused(self):
        # Selecting it would make projects.json editable through the file API.
        self.refused(self.folder)

    def test_a_specific_project_folder_is_allowed(self):
        self.assertEqual(self.store.select(str(self.project)), self.project)
        self.assertTrue(root_allowed(self.project, self.state))

    def test_a_tampered_profile_root_is_rejected_on_use(self):
        self.store.select(str(self.project))
        path = self.state / "projects.json"
        profile = json.loads(path.read_text("utf-8"))
        profile["root"] = str(Path(self.folder.anchor))
        path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaises(WorkspaceError) as error:
            self.store.workspace_root("project")
        self.assertEqual(error.exception.status, 409)

    def test_profile_edit_through_the_api_cannot_escape(self):
        app = create_app({"TESTING": True})
        mount(app, "tok", self.state, port=8760)
        client = app.test_client()
        headers = {"Authorization": "Bearer tok", "X-Workspace": "project"}
        response = client.post(
            PREFIX + "/project", base_url=BASE, headers=headers, json={"path": str(self.folder)}
        )
        self.assertEqual(response.status_code, 400)
        self.addCleanup(app.extensions["workbench"]["terminals"].shutdown)


class PrivateNameTest(unittest.TestCase):
    def test_ssh_and_credential_files_are_never_opened(self):
        for name in ("authorized_keys", "known_hosts", "id_ecdsa", "id_ed25519_sk", "id_dsa", "credentials"):
            self.assertFalse(component(name), name)
        for name in ("id_mapping.csv", "id_rsa.pub", "known_hosts_notes.md"):
            self.assertTrue(component(name), name)

    def test_windows_short_names_are_refused_only_on_windows(self):
        self.assertTrue(component("SSH~1"))
        with patch.object(files.os, "name", "nt"):
            for name in ("SSH~1", "CREDEN~1.JSO", "GIT~2"):
                self.assertFalse(component(name), name)
            self.assertTrue(component("notes~draft.txt"))


@unittest.skipIf(os.name == "nt", "POSIX mode bits")
class OwnerOnlyStorageTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_private_writes_are_owner_only_and_atomic(self):
        path = write_private(self.folder / "private.json", '{"a": 1}')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        write_private(path, '{"a": 2}')
        self.assertEqual(path.read_text("utf-8"), '{"a": 2}')
        self.assertEqual([item.name for item in self.folder.iterdir()], ["private.json"])

    def test_streamed_private_file_refuses_to_overwrite(self):
        path = self.folder / "dump.sql"
        with open_private(path) as stream:
            stream.write(b"--")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            open_private(path)

    def test_exposed_location_warns_once_or_raises_in_strict_mode(self):
        path = self.folder / "exposed.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)  # what a filesystem without POSIX modes leaves behind
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertFalse(check_private(path))
            self.assertFalse(check_private(path))
        self.assertEqual(len([item for item in caught if item.category is RuntimeWarning]), 1)
        with patch.dict(os.environ, {"LOGSENSE_STRICT_PERMISSIONS": "1"}):
            with self.assertRaises(InsecurePermissions):
                check_private(path)


class RuntimeBackupTest(unittest.TestCase):
    def test_backup_inside_the_runtime_directory_is_refused(self):
        from scripts.run import mysql_runtime

        root = (
            Path(mysql_runtime.__file__).resolve().parents[2] / ".local" / "unit-test-runtime-never-created"
        )
        with patch.object(mysql_runtime, "status"), patch.object(mysql_runtime, "load", return_value={}):
            with self.assertRaises(ValueError):
                mysql_runtime.backup(root, "logsense_dev", root / "backup.sql")
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
