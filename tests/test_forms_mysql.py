"""Live signed form/RBAC workflows on fresh token-guarded MySQL fixtures.

Form CSRF is never disabled. Only newly registered fixture metadata is deleted;
retained logs, source rows and existing datasets are not touched by these tests.
"""

import io
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

import test_dataset_crud_mysql as crud
from app.domain import User, UserDataset
from app.models import Dataset, DataSource, SourceArtifact


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Signed form MySQL integration NOT RUN (explicit isolated-schema opt-in required)",
)
class SignedFormsMySQLTests(unittest.TestCase):
    # Reuse fixture functions, not a TestCase subclass, so discovery does not
    # execute the entire CRUD suite again through inheritance/imported classes.
    setUpClass = classmethod(crud.DatasetCRUDMySQLTests.setUpClass.__func__)
    setUp = crud.DatasetCRUDMySQLTests.setUp
    tearDown = crud.DatasetCRUDMySQLTests.tearDown
    login = crud.DatasetCRUDMySQLTests.login
    headers = crud.DatasetCRUDMySQLTests.headers
    count = crud.DatasetCRUDMySQLTests.count

    def token(self, client=None):
        response = (client or self.client).get("/api/v1/forms/csrf")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsInstance(response.json["csrf_token"], str)
        return response.json["csrf_token"]

    def create_form(self, **changes):
        data = {
            "name": "Signed form fixture",
            "dataset_key": uuid4().hex,
            "data_mode": "unverified",
            "csrf_token": self.token(),
        }
        data.update(changes)
        return self.client.post("/forms/datasets", data=data, headers=self.headers())

    def other_client(self, role="manager"):
        with Session(self.engine) as session, session.begin():
            user = User(
                username=uuid4().hex,
                role=role,
                password_hash=generate_password_hash("synthetic-password-123"),
            )
            session.add(user)
            session.flush()
            session.add(UserDataset(user_id=user.id, dataset_id=self.dataset_id))
            username = user.username
        client = self.app.test_client()
        response = client.post(
            "/api/v1/auth/login", json={"username": username, "password": "synthetic-password-123"}
        )
        self.assertEqual(response.status_code, 200, response.json)
        return client, response.json["csrf_token"]

    def test_01_signed_token_endpoint_requires_active_session(self):
        self.assertEqual(self.client.get("/api/v1/forms/csrf").status_code, 403)
        self.login("viewer")
        self.assertTrue(self.app.config.get("WTF_CSRF_ENABLED", True))
        self.assertTrue(self.app.config.get("WTF_CSRF_CHECK_DEFAULT", True))
        self.assertTrue(self.token())

    def test_02_actual_form_create_rename_and_physical_empty_delete(self):
        creator = self.login("admin")
        response = self.create_form(name="Dữ liệu qua biểu mẫu")
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        item = response.json["dataset"]
        dataset_id = item["id"]
        self.assertEqual(response.headers["Location"], f"/api/v1/datasets/{dataset_id}")
        self.assertEqual(
            self.count(UserDataset, UserDataset.dataset_id == dataset_id, UserDataset.user_id == creator), 1
        )
        renamed = self.client.post(
            f"/forms/datasets/{dataset_id}/rename",
            data={"name": "Renamed through Flask-WTF", "csrf_token": self.token()},
            headers=self.headers(),
        )
        self.assertEqual(renamed.status_code, 200, renamed.json)
        self.assertEqual(renamed.headers["Cache-Control"], "no-store")
        self.assertEqual(renamed.json["dataset"]["name"], "Renamed through Flask-WTF")
        self.assertEqual(renamed.json["dataset"]["input_revision"], 0)
        self.assertEqual(renamed.json["dataset"]["dataset_key"], item["dataset_key"])
        deleted = self.client.post(
            f"/forms/datasets/{dataset_id}/delete",
            data={"confirmation": "y", "csrf_token": self.token()},
            headers=self.headers(),
        )
        self.assertEqual(deleted.status_code, 204, deleted.data)
        self.assertEqual(deleted.headers["Cache-Control"], "no-store")
        self.assertEqual(self.count(Dataset, Dataset.id == dataset_id), 0)
        self.assertEqual(self.count(UserDataset, UserDataset.dataset_id == dataset_id), 0)
        self.assertEqual(self.count(DataSource, DataSource.id == item["source_id"]), 1)

    def test_03_all_mutations_require_both_csrf_guards(self):
        self.login("admin")
        signed = self.token()
        original = self.client.get(f"/api/v1/datasets/{self.dataset_id}").json["dataset"]
        cases = [
            (
                "/forms/datasets",
                {"name": "CSRF fixture", "dataset_key": uuid4().hex, "data_mode": "unverified"},
            ),
            (f"/forms/datasets/{self.dataset_id}/rename", {"name": "Must not change"}),
            (f"/forms/datasets/{self.dataset_id}/delete", {"confirmation": "y"}),
        ]
        for path, fields in cases:
            for headers in ({}, {"X-CSRF-Token": "incorrect-header"}):
                with self.subTest(path=path, gate="header"):
                    response = self.client.post(path, data=dict(fields, csrf_token=signed), headers=headers)
                    self.assertEqual(response.status_code, 403, response.json)
            for token in (None, "forged-form-token"):
                with self.subTest(path=path, gate="form"):
                    data = dict(fields)
                    if token is not None:
                        data["csrf_token"] = token
                    response = self.client.post(path, data=data, headers=self.headers())
                    self.assertEqual(response.status_code, 400, response.json)
                    self.assertIn("csrf_token", response.json["error"]["fields"])
        self.assertEqual(self.client.get(f"/api/v1/datasets/{self.dataset_id}").json["dataset"], original)

    def test_04_cross_session_form_token_rejected_with_valid_header(self):
        self.login("admin")
        own = self.token()
        other, other_header = self.other_client()
        foreign = self.token(other)
        response = self.client.post(
            f"/forms/datasets/{self.dataset_id}/rename",
            data={"name": "Wrong session", "csrf_token": foreign},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertIn("csrf_token", response.json["error"]["fields"])
        response = other.post(
            "/forms/datasets",
            data={
                "name": "Wrong session",
                "dataset_key": uuid4().hex,
                "data_mode": "unverified",
                "csrf_token": own,
            },
            headers={"X-CSRF-Token": other_header},
        )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertIn("csrf_token", response.json["error"]["fields"])

    def test_05_expired_form_token_rejected_and_fresh_token_works(self):
        self.login("manager")
        signed = self.token()
        with patch.dict(self.app.config, {"WTF_CSRF_TIME_LIMIT": -1}):
            response = self.client.post(
                f"/forms/datasets/{self.dataset_id}/rename",
                data={"name": "Expired attempt", "csrf_token": signed},
                headers=self.headers(),
            )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertIn("expired", response.json["error"]["fields"]["csrf_token"][0].lower())
        valid = self.client.post(
            f"/forms/datasets/{self.dataset_id}/rename",
            data={"name": "Fresh token accepted", "csrf_token": self.token()},
            headers=self.headers(),
        )
        self.assertEqual(valid.status_code, 200, valid.json)

    def test_06_role_matrix_applies_to_form_adapters(self):
        for role in ("viewer", "analyst", "manager", "admin"):
            with self.subTest(role=role):
                self.login(role)
                token = self.token()
                created = self.create_form()
                self.assertEqual(created.status_code, 201 if role in {"manager", "admin"} else 403)
                renamed = self.client.post(
                    f"/forms/datasets/{self.dataset_id}/rename",
                    data={"name": "Role " + role, "csrf_token": token},
                    headers=self.headers(),
                )
                self.assertEqual(renamed.status_code, 200 if role in {"manager", "admin"} else 403)
                removed = self.client.post(
                    f"/forms/datasets/{self.dataset_id}/delete",
                    data={"confirmation": "y", "csrf_token": token},
                    headers=self.headers(),
                )
                self.assertEqual(removed.status_code, 204 if role == "admin" else 403)

    def test_07_admin_has_no_ungranted_form_access(self):
        self.login("admin")
        token = self.token()
        for dataset in (self.other_id, 2**63 - 1):
            self.assertEqual(
                self.client.post(
                    f"/forms/datasets/{dataset}/rename",
                    data={"name": "Forbidden", "csrf_token": token},
                    headers=self.headers(),
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    f"/forms/datasets/{dataset}/delete",
                    data={"confirmation": "y", "csrf_token": token},
                    headers=self.headers(),
                ).status_code,
                403,
            )

    def test_08_duplicate_form_key_conflicts_without_new_dataset(self):
        self.login("manager")
        key = uuid4().hex
        first = self.create_form(dataset_key=key)
        self.assertEqual(first.status_code, 201, first.json)
        source_id = first.json["dataset"]["source_id"]
        count_before = self.count(Dataset, Dataset.source_id == source_id)
        duplicate = self.create_form(dataset_key=key)
        self.assertEqual(duplicate.status_code, 409, duplicate.json)
        self.assertEqual(duplicate.json["error"]["code"], "dataset_conflict")
        self.assertEqual(self.count(Dataset, Dataset.source_id == source_id), count_before)

    def test_09_malformed_types_unknown_and_duplicate_fields_are400(self):
        self.login("manager")
        response = self.client.post("/forms/datasets", json=["not", "form"], headers=self.headers())
        self.assertEqual(response.status_code, 400, response.json)
        response = self.create_form(state="imported")
        self.assertEqual(response.status_code, 400, response.json)
        response = self.create_form(source_id="1.2")
        self.assertEqual(response.status_code, 400, response.json)
        response = self.client.post(
            "/forms/datasets",
            data=MultiDict(
                [
                    ("name", "First"),
                    ("name", "Second"),
                    ("dataset_key", uuid4().hex),
                    ("data_mode", "real"),
                    ("csrf_token", self.token()),
                ]
            ),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400, response.json)
        response = self.client.post(
            "/forms/datasets",
            data={
                "name": "Unexpected file",
                "dataset_key": uuid4().hex,
                "data_mode": "unverified",
                "csrf_token": self.token(),
                "file": (io.BytesIO(b"test"), "not-allowed.txt"),
            },
            headers=self.headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400, response.json)

    def test_10_delete_requires_confirmation_and_preserves_related_rows(self):
        self.login("admin")
        missing = self.client.post(
            f"/forms/datasets/{self.dataset_id}/delete",
            data={"csrf_token": self.token()},
            headers=self.headers(),
        )
        self.assertEqual(missing.status_code, 400, missing.json)
        with Session(self.engine) as session, session.begin():
            session.add(
                SourceArtifact(
                    dataset_id=self.dataset_id,
                    artifact_key=uuid4().hex,
                    sha256="a" * 64,
                    byte_length=0,
                    parser_version="synthetic-form-fixture",
                )
            )
        response = self.client.post(
            f"/forms/datasets/{self.dataset_id}/delete",
            data={"confirmation": "y", "csrf_token": self.token()},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(self.count(Dataset, Dataset.id == self.dataset_id), 1)
        self.assertEqual(self.count(SourceArtifact, SourceArtifact.dataset_id == self.dataset_id), 1)
        self.assertEqual(self.count(UserDataset, UserDataset.dataset_id == self.dataset_id), 1)

    def test_11_delete_failure_after_acl_change_rolls_back(self):
        self.login("admin")
        with patch(
            "app.services.dataset_management._delete_dataset_row",
            side_effect=OperationalError("synthetic-sensitive-query", {}, Exception("synthetic-db-failure")),
        ):
            response = self.client.post(
                f"/forms/datasets/{self.dataset_id}/delete",
                data={"confirmation": "y", "csrf_token": self.token()},
                headers=self.headers(),
            )
        self.assertEqual(response.status_code, 503, response.json)
        self.assertNotIn("synthetic", response.get_data(as_text=True))
        self.assertEqual(self.count(Dataset, Dataset.id == self.dataset_id), 1)
        self.assertEqual(self.count(UserDataset, UserDataset.dataset_id == self.dataset_id), 1)

    def test_12_logged_out_and_disabled_identity_cannot_replay_form(self):
        actor = self.login("admin")
        token = self.token()
        response = self.client.post("/api/v1/auth/logout", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/forms/datasets",
            data={
                "name": "Logged out",
                "dataset_key": uuid4().hex,
                "data_mode": "unverified",
                "csrf_token": token,
            },
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 403)
        actor = self.login("admin")
        token = self.token()
        with Session(self.engine) as session, session.begin():
            session.get(User, actor).active = False
        response = self.client.post(
            "/forms/datasets",
            data={
                "name": "Disabled",
                "dataset_key": uuid4().hex,
                "data_mode": "unverified",
                "csrf_token": token,
            },
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 403)

    def test_13_existing_rest_json_contract_does_not_need_form_token(self):
        self.login("manager")
        with self.client.session_transaction() as state:
            self.assertNotIn("csrf_token", state)
        response = self.client.post(
            "/api/v1/datasets",
            json={"name": "Existing JSON API", "dataset_key": uuid4().hex},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 201, response.json)

    def test_14_form_source_id_cannot_attach_to_ungranted_source(self):
        self.login("manager")
        with Session(self.engine) as session, session.begin():
            source = DataSource(source_key=uuid4().hex, name="Private isolated source fixture")
            session.add(source)
            session.flush()
            source_id = source.id
            session.add(
                Dataset(
                    source_id=source_id,
                    dataset_key=uuid4().hex,
                    name="Ungranted source fixture",
                    data_mode="synthetic",
                )
            )
        response = self.create_form(source_id=str(source_id))
        self.assertEqual(response.status_code, 403, response.json)
        self.assertNotIn("Private isolated", response.get_data(as_text=True))
