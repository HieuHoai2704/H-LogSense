"""The sign-in gate and account pages without a database: everything private redirects to sign-in."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from app.web_accounts import safe_next


class SignInGateTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_app(
            {"TESTING": True, "LOGIN_REQUIRED": True, "SECRET_KEY": "synthetic-gate-secret"}
        )
        self.client = self.app.test_client()

    def mount_workbench(self, app):
        from app.workbench.api import mount

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        local = mount(app, "synthetic-workbench-token", Path(folder.name), port=None)
        self.addCleanup(local["terminals"].shutdown)

    def test_served_apps_require_sign_in_by_default_and_test_apps_opt_in(self):
        self.assertTrue(create_app({"SECRET_KEY": "x"}).config["LOGIN_REQUIRED"])
        self.assertFalse(create_app({"TESTING": True}).config["LOGIN_REQUIRED"])

    def test_every_workspace_page_redirects_to_sign_in(self):
        for path, target in (
            ("/", "/account/login"),
            ("/?view=editor", "/account/login?next=/?view%3Deditor"),
            ("/?workspace=logs", "/account/login?next=/?workspace%3Dlogs"),
            ("/?source=demo", "/account/login?next=/?source%3Ddemo"),
            ("/manage/datasets", "/account/login?next=/manage/datasets"),
            ("/account/admin/users", "/account/login?next=/account/admin/users"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path, headers={"Accept": "text/html"})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], target)

    def test_api_fragments_and_writes_answer_401_json(self):
        self.mount_workbench(self.app)
        for method, path, headers in (
            ("get", "/api/v1/logs/datasets", {}),
            ("get", "/api/local/v1/session", {"Authorization": "Bearer synthetic-workbench-token"}),
            ("get", "/?source=demo", {"X-Workspace-Fragment": "1"}),
            ("post", "/api/v1/datasets", {}),
        ):
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json["error"]["code"], "login_required")
                self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_service_token_still_reaches_the_read_api(self):
        app = create_app(
            {
                "SECRET_KEY": "x",
                "DATABASE_READ_TOKEN": "synthetic-operator-token",
                "DATABASE_ALLOWED_DATASETS": (1,),
            }
        )
        self.mount_workbench(app)
        client = app.test_client()
        # Past the gate: no database is configured, so the API itself answers 503.
        ok = client.get("/api/v1/logs/datasets", headers={"Authorization": "Bearer synthetic-operator-token"})
        self.assertEqual(ok.status_code, 503)
        wrong = client.get("/api/v1/logs/datasets", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(wrong.status_code, 401)
        # The service token never opens the local workbench API.
        local = client.get(
            "/api/local/v1/session", headers={"Authorization": "Bearer synthetic-operator-token"}
        )
        self.assertEqual(local.status_code, 401)

    def test_sign_in_pages_are_public_and_carry_both_portals(self):
        for path, marker in (
            ("/account/login", 'action="/account/login"'),
            ("/account/admin", 'action="/account/admin"'),
            ("/account/forgot", 'name="email"'),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                self.assertIn(marker, body)
                self.assertIn('href="/account/admin"', body)
                self.assertIn('name="csrf_token"', body)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        admin = self.client.get("/account/admin").get_data(as_text=True)
        self.assertIn('class="auth-card admin"', admin)

    def test_there_is_no_self_registration(self):
        # Only an administrator creates accounts (user management).
        staff = self.client.get("/account/login").get_data(as_text=True)
        self.assertNotIn("/account/register", staff)
        self.assertEqual(self.client.get("/account/register").status_code, 404)
        self.assertEqual(self.client.post("/account/register").status_code, 404)

    def test_sign_in_without_database_is_503_not_a_crash(self):
        page = self.client.get("/account/login").get_data(as_text=True)
        self.assertIn("Accounts need the MySQL database", page)
        self.app.config["WTF_CSRF_ENABLED"] = False
        response = self.client.post(
            "/account/login", data={"username": "a", "password": "b", "portal": "staff"}
        )
        self.assertEqual(response.status_code, 503)

    def test_forms_reject_missing_csrf(self):
        response = self.client.post("/account/login", data={"username": "a", "password": "b"})
        self.assertIn(response.status_code, {400, 503})
        self.assertEqual(self.client.post("/account/logout").status_code, 401)

    def test_next_is_limited_to_same_site_paths(self):
        self.assertEqual(safe_next("/?workspace=logs"), "/?workspace=logs")
        self.assertEqual(safe_next("/manage/datasets"), "/manage/datasets")
        for value in (
            None,
            "",
            "https://example.org/",
            "//example.org/",
            "/\\example.org",
            "javascript:alert(1)",
            "/account/logout",
        ):
            with self.subTest(value=value):
                self.assertIsNone(safe_next(value))


if __name__ == "__main__":
    unittest.main()
