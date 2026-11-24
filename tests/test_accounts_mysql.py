"""Account pages on real MySQL: two sign-in portals, sign-out, password reset and the administrator's
user management (create with a welcome email, search, paginate, edit, delete). Form CSRF stays enabled."""

import os
import re
import unittest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
import test_dataset_crud_mysql as crud
from werkzeug.security import generate_password_hash

from app.domain import User, UserDataset

PASSWORD = "synthetic-password-123"


def csrf(page, prefix=""):
    name = f"{prefix}-csrf_token" if prefix else "csrf_token"
    match = re.search(rf'name="{re.escape(name)}" type="hidden" value="([^"]+)"', page)
    if match is None:
        match = re.search(
            rf'id="{re.escape(name)}" name="{re.escape(name)}" type="hidden" value="([^"]+)"', page
        )
    assert match, f"no {name} on the page"
    return match.group(1)


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Account MySQL integration NOT RUN (explicit isolated-schema opt-in required)",
)
class AccountMySQLTests(unittest.TestCase):
    setUpClass = classmethod(crud.DatasetCRUDMySQLTests.setUpClass.__func__)
    tearDown = crud.DatasetCRUDMySQLTests.tearDown

    def setUp(self):
        crud.DatasetCRUDMySQLTests.setUp(self)
        self.app.config["LOGIN_REQUIRED"] = True
        self.addCleanup(self.app.config.update, LOGIN_REQUIRED=False)
        self.app.extensions["account_outbox"] = []

    def user(self, role="staff", *, email=None, active=True):
        with Session(self.engine) as session, session.begin():
            user = User(
                username="u" + uuid4().hex[:20],
                email=email,
                password_hash=generate_password_hash(PASSWORD),
                role=role,
                active=active,
            )
            session.add(user)
            session.flush()
            return user.id, user.username

    def sign_in(self, username, portal="staff", password=PASSWORD, next_path=None, client=None):
        from app.security import attempts

        attempts.clear()
        client = client or self.client
        path = "/account/admin" if portal == "admin" else "/account/login"
        prefix = "admin-" if portal == "admin" else ""
        page = client.get(path + (f"?next={next_path}" if next_path else "")).get_data(as_text=True)
        data = {
            prefix + "csrf_token": csrf(page, prefix.rstrip("-")),
            prefix + "username": username,
            prefix + "password": password,
            prefix + "portal": portal,
        }
        if next_path:
            data[prefix + "next"] = next_path
        return client.post(path, data=data)

    def page(self, path, client=None):
        response = (client or self.client).get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def create_account(self, form_page, **fields):
        data = {"csrf_token": csrf(form_page), "role": "staff", "password": PASSWORD, "confirm": PASSWORD}
        data.update(fields)
        return self.client.post("/account/admin/users", data=data)

    def test_01_admin_created_account_gets_welcome_mail_and_signs_in(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        _, admin = self.user("admin")
        self.sign_in(admin, "admin")
        username = "staff" + uuid4().hex[:12]
        email = f"{username}@example.invalid"
        response = self.create_account(
            self.page("/account/admin/users"), username=username, email=email.upper(), role="staff"
        )
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as session:
            user = session.scalar(select(User).where(User.username == username))
            self.assertEqual((user.email, user.role, user.active), (email, "staff", True))
            # A new account opens every existing dataset; the administrator can narrow this.
            grants = session.scalars(
                select(UserDataset.dataset_id).where(UserDataset.user_id == user.id)
            ).all()
            self.assertIn(self.dataset_id, grants)
            self.assertNotIn(PASSWORD, user.password_hash)
        (mail,) = self.app.extensions["account_outbox"]
        self.assertEqual(mail.recipients, [email])
        self.assertIn(username, mail.body)
        self.assertIn("/account/login", mail.html)
        # The new staff member signs in and sees the workspace with a sign-out form.
        staff = self.app.test_client()
        self.assertEqual(self.sign_in(username, client=staff).status_code, 303)
        workspace = self.page("/", client=staff)
        self.assertIn(username, workspace)
        self.assertIn('action="/account/logout"', workspace)
        # The same username or email cannot be created twice.
        again = self.create_account(self.page("/account/admin/users"), username=username, email=email)
        self.assertEqual(again.status_code, 303)
        self.assertEqual(len(self.app.extensions["account_outbox"]), 1)
        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(User).where(User.username == username)).all()), 1)

    def test_02_account_form_validates_every_field_and_needs_an_admin(self):
        _, admin = self.user("admin")
        self.sign_in(admin, "admin")
        page = self.page("/account/admin/users")
        response = self.create_account(
            page, username="a b", email="not-an-email", password="short", confirm="different"
        )
        self.assertEqual(response.status_code, 303)
        body = self.page("/account/admin/users")
        for message in (
            "Use 3-100 letters, numbers, dot, underscore or hyphen.",
            "Enter a valid email address.",
            "The passwords do not match.",
        ):
            self.assertIn(message, body)
        self.assertNotIn("Use at least 8 characters.", body)  # administrators may set short passwords
        self.assertEqual(self.app.extensions["account_outbox"], [])
        # A one-character password set by an administrator works.
        short = "s" + uuid4().hex[:10]
        made = self.create_account(
            self.page("/account/admin/users"),
            username=short,
            email=f"{short}@example.invalid",
            password="1",
            confirm="1",
        )
        self.assertEqual(made.status_code, 303)
        self.assertEqual(self.sign_in(short, password="1", client=self.app.test_client()).status_code, 303)
        # Staff use the whole application but never the account pages.
        _, staff = self.user("staff")
        other = self.app.test_client()
        self.sign_in(staff, client=other)
        self.assertEqual(other.get("/account/admin/users").status_code, 403)
        self.assertEqual(other.post("/account/admin/users", data={}).status_code, 403)

    def test_03_portals_admit_only_their_account_type(self):
        _, staff = self.user("staff")
        _, admin = self.user("admin")
        self.assertEqual(self.sign_in(staff, "admin").status_code, 403)
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.sign_in(admin, "staff").status_code, 403)
        self.assertEqual(self.sign_in(admin, "admin", password="wrong-password").status_code, 401)
        signed = self.sign_in(admin, "admin")
        self.assertEqual((signed.status_code, signed.headers["Location"]), (303, "/account/admin/users"))
        member = self.app.test_client()
        self.assertEqual(self.sign_in(staff, "staff", client=member).headers["Location"], "/")
        # Staff reach every workspace and the dataset pages.
        for path in ("/", "/?view=editor", "/?workspace=logs", "/manage/datasets"):
            self.assertEqual(member.get(path).status_code, 200, path)

    def test_04_next_path_and_sign_out_end_every_workspace(self):
        _, viewer = self.user("staff")
        redirect = self.client.get("/?workspace=logs")
        self.assertEqual(redirect.headers["Location"], "/account/login?next=/?workspace%3Dlogs")
        signed = self.sign_in(viewer, next_path="/?workspace=logs")
        self.assertEqual(signed.headers["Location"], "/?workspace=logs")
        for path in ("/", "/?view=editor", "/?workspace=logs", "/?source=demo"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        page = self.page("/")
        out = self.client.post("/account/logout", data={"csrf_token": csrf(page)})
        self.assertEqual((out.status_code, out.headers["Location"]), (303, "/account/login"))
        for path in ("/", "/?view=editor", "/?workspace=logs", "/?source=demo", "/manage/datasets"):
            self.assertEqual(self.client.get(path).status_code, 302, path)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        # An external next is ignored.
        self.assertEqual(self.sign_in(viewer, next_path="//example.org/").headers["Location"], "/")

    def test_05_sign_in_is_rate_limited(self):
        from app.security import attempts

        _, viewer = self.user("staff")
        attempts.clear()
        page = self.page("/account/login")
        token = csrf(page)
        codes = [
            self.client.post(
                "/account/login", data={"csrf_token": token, "username": viewer, "password": "wrong"}
            ).status_code
            for _ in range(6)
        ]
        self.assertEqual(codes, [401] * 5 + [429])

    def test_06_password_reset_link_works_once_and_ends_old_sessions(self):
        email = f"reset{uuid4().hex[:10]}@example.invalid"
        user_id, username = self.user("staff", email=email)
        old_session = self.app.test_client()
        self.sign_in(username, client=old_session)
        self.assertEqual(old_session.get("/").status_code, 200)

        page = self.page("/account/forgot")
        unknown = self.client.post(
            "/account/forgot", data={"csrf_token": csrf(page), "email": "nobody@example.invalid"}
        )
        self.assertEqual((unknown.status_code, self.app.extensions["account_outbox"]), (303, []))
        known = self.client.post("/account/forgot", data={"csrf_token": csrf(page), "email": email})
        self.assertEqual(known.status_code, 303)
        (message,) = self.app.extensions["account_outbox"]
        link = re.search(r"http://localhost(/account/reset/[A-Za-z0-9_.\-]+)", message.body).group(1)

        form = self.page(link)
        self.assertIn(username, form)
        changed = self.client.post(
            link,
            data={
                "csrf_token": csrf(form),
                "password": "new-synthetic-pass-1",
                "confirm": "new-synthetic-pass-1",
            },
        )
        self.assertEqual((changed.status_code, changed.headers["Location"]), (303, "/account/login"))
        self.assertEqual(old_session.get("/").status_code, 302)  # auth_version changed
        reused = self.client.get(link)
        self.assertEqual((reused.status_code, reused.headers["Location"]), (303, "/account/forgot"))
        self.assertEqual(self.sign_in(username).status_code, 401)
        self.assertEqual(self.sign_in(username, password="new-synthetic-pass-1").status_code, 303)
        self.assertEqual(self.client.get("/account/reset/forged-token").status_code, 404)
        with Session(self.engine) as session:
            self.assertEqual(session.get(User, user_id).auth_version, 2)

    def test_07_admin_creates_searches_pages_edits_and_deletes_accounts(self):
        admin_id, admin = self.user("admin")
        self.sign_in(admin, "admin")
        marker = uuid4().hex[:8]
        for index in range(23):
            self.user("staff", email=f"page{index:02d}-{marker}@example.invalid")

        listing = self.page("/account/admin/users")
        username = "made" + marker
        created = self.client.post(
            "/account/admin/users",
            data={
                "csrf_token": csrf(listing),
                "username": username,
                "email": f"{username}@example.invalid",
                "role": "staff",
                "password": PASSWORD,
                "confirm": PASSWORD,
            },
        )
        self.assertEqual(created.status_code, 303)
        with Session(self.engine) as session:
            made = session.scalar(select(User).where(User.username == username))
            self.assertEqual(made.role, "staff")

        found = self.page(f"/account/admin/users?q={marker}")
        self.assertEqual(found.count(f"-{marker}@example.invalid"), 20)  # one page of 20
        self.assertIn("page=2", found)
        second = self.page(f"/account/admin/users?q={marker}&page=2")
        self.assertEqual(second.count(f"-{marker}@example.invalid"), 3)
        self.assertIn(username, second)
        staff_only = self.page(f"/account/admin/users?q={marker}&role=staff")
        self.assertIn("Total accounts: 24", staff_only)  # 23 listed accounts and the one just added
        self.assertIn("No accounts match.", self.page(f"/account/admin/users?q={marker}&role=admin"))
        self.assertIn("No accounts match.", self.page("/account/admin/users?q=%25_nothing_"))

        edit = self.page(f"/account/admin/users/{made.id}")
        updated = self.client.post(
            f"/account/admin/users/{made.id}",
            data={
                "csrf_token": csrf(edit),
                "email": f"{username}@example.invalid",
                "role": "admin",
                "datasets": [str(self.dataset_id)],
            },
        )
        self.assertEqual(updated.status_code, 303)
        with Session(self.engine) as session:
            made = session.get(User, made.id)
            self.assertEqual((made.role, made.active, made.auth_version), ("admin", False, 2))
            grants = session.scalars(
                select(UserDataset.dataset_id).where(UserDataset.user_id == made.id)
            ).all()
            self.assertEqual(grants, [self.dataset_id])

        own = self.page(f"/account/admin/users/{admin_id}")
        refused = self.client.post(
            f"/account/admin/users/{admin_id}",
            data={"csrf_token": csrf(own), "role": "staff", "active": "y"},
        )
        self.assertEqual(refused.status_code, 400)
        self.assertIn("You cannot remove your own administrator access.", refused.get_data(as_text=True))

        edit = self.page(f"/account/admin/users/{made.id}")
        unconfirmed = self.client.post(
            f"/account/admin/users/{made.id}/delete", data={"delete-csrf_token": csrf(edit, "delete")}
        )
        self.assertEqual(unconfirmed.headers["Location"], f"/account/admin/users/{made.id}")
        deleted = self.client.post(
            f"/account/admin/users/{made.id}/delete",
            data={"delete-csrf_token": csrf(edit, "delete"), "delete-confirmation": "y"},
        )
        self.assertEqual((deleted.status_code, deleted.headers["Location"]), (303, "/account/admin/users"))
        with Session(self.engine) as session:
            self.assertIsNone(session.get(User, made.id))
            self.assertIsNotNone(session.get(User, admin_id))

    def sign_up(self, username, email, password=PASSWORD, confirm=None, client=None):
        from app.security import attempts

        attempts.clear()
        client = client or self.client
        page = client.get("/account/register").get_data(as_text=True)
        return client.post(
            "/account/register",
            data={
                "signup-csrf_token": csrf(page, "signup"),
                "signup-username": username,
                "signup-email": email,
                "signup-password": password,
                "signup-confirm": confirm or password,
            },
        )

    def test_08_sign_up_waits_for_approval_then_signs_in(self):
        admin_id, admin = self.user("admin", email=f"adm{uuid4().hex[:8]}@example.invalid")
        username = "su" + uuid4().hex[:10]
        email = f"{username}@example.invalid"
        response = self.sign_up(username, email.upper())
        self.assertEqual((response.status_code, response.headers["Location"]), (303, "/account/login"))
        with Session(self.engine) as session:
            user = session.scalar(select(User).where(User.username == username))
            self.assertEqual(
                (user.email, user.role, user.active, user.pending), (email, "staff", False, True)
            )
            self.assertEqual(
                session.scalars(select(UserDataset).where(UserDataset.user_id == user.id)).all(), []
            )
            user_id = user.id
        sent = {tuple(m.recipients): m for m in self.app.extensions["account_outbox"]}
        self.assertIn((email,), sent)  # "registration received" to the new user
        admin_mail = [m for m in self.app.extensions["account_outbox"] if m.recipients != [email]]
        self.assertTrue(any(username in m.body and "state=pending" in m.body for m in admin_mail))
        # The right password is told to wait; a wrong one stays a generic failure.
        waiting = self.sign_in(username)
        self.assertEqual(waiting.status_code, 403)
        self.assertIn("waiting for administrator approval", waiting.get_data(as_text=True))
        self.assertEqual(self.sign_in(username, password="wrong-password").status_code, 401)
        # Duplicates and a mismatched confirmation are refused.
        self.assertEqual(self.sign_up(username, "other@example.invalid").status_code, 409)
        self.assertEqual(self.sign_up("x" + username, "y" + email, confirm="different-pass").status_code, 400)

        reviewer = self.app.test_client()
        self.sign_in(admin, "admin", client=reviewer)
        listing = self.page("/account/admin/users?state=pending", client=reviewer)
        self.assertIn(username, listing)
        self.assertIn("Sign-up requests waiting for approval: ", listing)
        self.app.extensions["account_outbox"] = []
        approved = reviewer.post(
            f"/account/admin/users/{user_id}/approve", data={"csrf_token": csrf(listing)}
        )
        self.assertEqual(approved.status_code, 303)
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            self.assertEqual((user.active, user.pending), (True, False))
            grants = session.scalars(
                select(UserDataset.dataset_id).where(UserDataset.user_id == user_id)
            ).all()
            self.assertIn(self.dataset_id, grants)
        (mail,) = self.app.extensions["account_outbox"]
        self.assertEqual(mail.recipients, [email])
        self.assertIn("/account/login", mail.body)
        self.assertEqual(self.sign_in(username).status_code, 303)
        # A decided account cannot be decided again; CSRF is required.
        self.assertEqual(reviewer.post(f"/account/admin/users/{user_id}/reject", data={}).status_code, 400)
        again = reviewer.post(f"/account/admin/users/{user_id}/reject", data={"csrf_token": csrf(listing)})
        self.assertEqual(again.status_code, 303)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(User, user_id))
        self.assertNotEqual(admin_id, user_id)

    def test_09_rejected_sign_up_is_deleted_and_staff_cannot_decide(self):
        _, admin = self.user("admin")
        username = "rj" + uuid4().hex[:10]
        email = f"{username}@example.invalid"
        self.assertEqual(self.sign_up(username, email).status_code, 303)
        with Session(self.engine) as session:
            user_id = session.scalar(select(User.id).where(User.username == username))
        _, staff = self.user("staff")
        member = self.app.test_client()
        self.sign_in(staff, client=member)
        page = self.page("/", client=member)
        self.assertEqual(
            member.post(
                f"/account/admin/users/{user_id}/approve", data={"csrf_token": csrf(page)}
            ).status_code,
            403,
        )
        reviewer = self.app.test_client()
        self.sign_in(admin, "admin", client=reviewer)
        listing = self.page("/account/admin/users?state=pending", client=reviewer)
        self.app.extensions["account_outbox"] = []
        rejected = reviewer.post(f"/account/admin/users/{user_id}/reject", data={"csrf_token": csrf(listing)})
        self.assertEqual(rejected.status_code, 303)
        with Session(self.engine) as session:
            self.assertIsNone(session.get(User, user_id))
        (mail,) = self.app.extensions["account_outbox"]
        self.assertEqual(mail.recipients, [email])
        self.assertIn("did not approve", mail.body)


if __name__ == "__main__":
    unittest.main()
