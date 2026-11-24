"""Dataset lifecycle/RBAC against token-guarded, isolated real MySQL schemas.

Only newly created fixture metadata is deleted. Imported records, source rows
and all existing user datasets are retained. DELETE privileges are table scoped.
"""

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import os
import re
from threading import Barrier
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

import test_mysql_integration as baseline
from app.domain import User, UserDataset
from app.models import (
    CoverageInterval,
    DataSource,
    Dataset,
    ProcessingJob,
    SourceArtifact,
)


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Dataset CRUD MySQL integration NOT RUN (explicit opt-in required)",
)
class DatasetCRUDMySQLTests(unittest.TestCase):
    tearDown = baseline.MySQLIntegrationTests.tearDown

    @classmethod
    def setUpClass(cls):
        baseline.MySQLIntegrationTests.setUpClass.__func__(cls)
        url = cls.engine.url
        admin_url = make_url(os.environ["MYSQL_ADMIN_URL"])
        if (
            (admin_url.host, admin_url.port) != (url.host, url.port)
            or not re.fullmatch(r"logsense_test_[0-9a-f]{12}", url.database or "")
            or not re.fullmatch(r"[a-zA-Z0-9_]+", url.username or "")
        ):
            raise RuntimeError("Refusing privilege changes outside the owned test schema")
        # Tables exist after baseline migration. Never grant schema-wide DELETE.
        admin = create_engine(admin_url, hide_parameters=True)
        try:
            with admin.begin() as connection:
                for table in ("datasets", "user_datasets"):
                    connection.execute(
                        text(f"GRANT DELETE ON `{url.database}`.`{table}` TO '{url.username}'@'localhost'")
                    )
        finally:
            admin.dispose()
        # New connections observe the exact newly granted table privileges.
        cls.engine.dispose()

    def setUp(self):
        baseline.MySQLIntegrationTests.setUp(self)
        from app.security import attempts

        attempts.clear()
        self.app.config["SECRET_KEY"] = "synthetic-dataset-crud-session-secret"
        self.client = self.app.test_client()

    def login(self, role="admin", *, grant=True):
        from app.security import attempts

        attempts.clear()
        with Session(self.engine) as session, session.begin():
            user = User(
                username=uuid4().hex,
                password_hash=generate_password_hash("synthetic-password-123"),
                role=role,
            )
            session.add(user)
            session.flush()
            self.user_id, username = user.id, user.username
            if grant:
                session.add(UserDataset(user_id=user.id, dataset_id=self.dataset_id))
        result = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": username,
                "password": "synthetic-password-123",
            },
        )
        self.assertEqual(result.status_code, 200, result.json)
        self.csrf = result.json["csrf_token"]
        return self.user_id

    def headers(self):
        return {"X-CSRF-Token": self.csrf}

    def create(self, **changes):
        body = {"name": "Synthetic CRUD fixture", "dataset_key": uuid4().hex}
        body.update(changes)
        return self.client.post("/api/v1/datasets", json=body, headers=self.headers())

    def resource(self, result):
        return result.json["dataset"]

    def count(self, model, *where):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(model).where(*where))

    def test_01_create_read_update_delete_is_actual_atomic_sql_crud(self):
        creator = self.login("admin")
        created = self.create(name="Dữ liệu kiểm thử", data_mode="unverified")
        self.assertEqual(created.status_code, 201, created.json)
        item = self.resource(created)
        dataset_id = item["id"]
        self.assertEqual(item["name"], "Dữ liệu kiểm thử")
        self.assertEqual((item["state"], item["input_revision"]), ("registered", 0))
        self.assertEqual(
            self.count(UserDataset, UserDataset.user_id == creator, UserDataset.dataset_id == dataset_id), 1
        )
        detail = self.client.get(f"/api/v1/datasets/{dataset_id}")
        self.assertEqual(detail.status_code, 200, detail.json)
        self.assertEqual(self.resource(detail)["id"], dataset_id)
        updated = self.client.patch(
            f"/api/v1/datasets/{dataset_id}", json={"name": "Renamed fixture"}, headers=self.headers()
        )
        self.assertEqual(updated.status_code, 200, updated.json)
        self.assertEqual(self.resource(updated)["name"], "Renamed fixture")
        self.assertEqual(self.resource(updated)["input_revision"], 0)
        deleted = self.client.delete(f"/api/v1/datasets/{dataset_id}", headers=self.headers())
        self.assertEqual(deleted.status_code, 204, deleted.data)
        self.assertEqual(self.count(Dataset, Dataset.id == dataset_id), 0)
        self.assertEqual(self.count(UserDataset, UserDataset.dataset_id == dataset_id), 0)
        self.assertEqual(self.count(DataSource, DataSource.id == item["source_id"]), 1)
        self.assertEqual(self.client.get(f"/api/v1/datasets/{dataset_id}").status_code, 403)

    def test_server_rendered_crud_keeps_csrf_permissions_and_prg(self):
        path = "/manage/datasets"
        self.assertEqual(self.client.get(path).status_code, 302)
        self.login("admin")

        def form_token(url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            return re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)[1].decode()

        key = uuid4().hex
        fields = {"name": "Server rendered fixture", "dataset_key": key, "data_mode": "unverified"}
        self.assertEqual(self.client.post(path, data=fields).status_code, 400)
        self.assertEqual(self.count(Dataset, Dataset.dataset_key == key), 0)
        created = self.client.post(path, data={**fields, "csrf_token": form_token(path)})
        self.assertEqual(created.status_code, 303)
        self.assertIn(b"Dataset created.", self.client.get(created.location).data)
        self.assertEqual(self.count(Dataset, Dataset.dataset_key == key), 1)
        row = next(x for x in self.client.get("/api/v1/datasets").json["items"] if x["dataset_key"] == key)
        rename = f"{path}/{row['id']}/rename"
        response = self.client.post(
            rename, data={"csrf_token": form_token(rename), "name": "Renamed in HTML"}
        )
        self.assertEqual(response.status_code, 303)
        self.assertIn(b"Renamed in HTML", self.client.get(response.location).data)
        delete_path = f"{path}/{row['id']}/delete"
        response = self.client.post(
            delete_path, data={"csrf_token": form_token(delete_path), "confirmation": "y"}
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.count(Dataset, Dataset.id == row["id"]), 0)
        self.login("viewer")
        self.assertNotIn(b"Register dataset", self.client.get(path).data)
        self.assertEqual(self.client.post(path, data=fields).status_code, 403)

    def test_02_role_matrix_and_explicit_grants(self):
        for role in ("viewer", "analyst", "manager", "admin"):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.client.get("/api/v1/datasets").status_code, 200)
                self.assertEqual(self.client.get(f"/api/v1/datasets/{self.dataset_id}").status_code, 200)
                result = self.create()
                self.assertEqual(result.status_code, 201 if role in {"manager", "admin"} else 403)
                changed = self.client.patch(
                    f"/api/v1/datasets/{self.dataset_id}",
                    json={"name": "Name after " + role},
                    headers=self.headers(),
                )
                self.assertEqual(changed.status_code, 200 if role in {"manager", "admin"} else 403)
                deleted = self.client.delete(f"/api/v1/datasets/{self.dataset_id}", headers=self.headers())
                self.assertEqual(deleted.status_code, 204 if role == "admin" else 403)

    def test_03_admin_has_no_implicit_cross_dataset_access(self):
        self.login("admin")
        listed = self.client.get("/api/v1/datasets").json["items"]
        self.assertEqual([r["id"] for r in listed], [self.dataset_id])
        for dataset_id in (self.other_id, 2**63 - 1):
            with self.subTest(dataset=dataset_id):
                self.assertEqual(self.client.get(f"/api/v1/datasets/{dataset_id}").status_code, 403)
                self.assertEqual(
                    self.client.patch(
                        f"/api/v1/datasets/{dataset_id}", json={"name": "Forbidden"}, headers=self.headers()
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.delete(f"/api/v1/datasets/{dataset_id}", headers=self.headers()).status_code,
                    403,
                )

    def test_04_empty_authenticated_list_and_anonymous_denial(self):
        self.assertEqual(self.client.get("/api/v1/logs/datasets").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/datasets").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/datasets", json={}).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/v1/datasets/{self.dataset_id}", json={}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/v1/datasets/{self.dataset_id}").status_code, 403)
        self.login("viewer", grant=False)
        response = self.client.get("/api/v1/datasets")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["items"], [])
        response = self.client.get("/api/v1/logs/datasets")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"datasets": []})
        self.assertEqual(self.client.get("/api/v1/logs").status_code, 403)
        self.assertEqual(self.create().status_code, 403)

    def test_first_dataset_appears_after_manager_creates_it(self):
        self.login("manager", grant=False)
        self.assertEqual(self.client.get("/api/v1/logs/datasets").json, {"datasets": []})
        dataset = self.resource(self.create())
        listed = self.client.get("/api/v1/logs/datasets").json["datasets"]
        self.assertEqual([item["id"] for item in listed], [dataset["id"]])
        self.assertEqual(self.client.get(f"/api/v1/investigation?source=db-{self.other_id}").status_code, 403)

    def test_05_read_token_cannot_mutate_or_bypass_session_roles(self):
        token = "synthetic-read-only-token"
        self.app.config.update(DATABASE_READ_TOKEN=token, DATABASE_ALLOWED_DATASETS=(self.dataset_id,))
        self.addCleanup(self.app.config.pop, "DATABASE_READ_TOKEN", None)
        self.addCleanup(self.app.config.pop, "DATABASE_ALLOWED_DATASETS", None)
        headers = {"Authorization": "Bearer " + token}
        self.assertEqual(self.client.get("/api/v1/datasets", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/datasets", json={}, headers=headers).status_code, 403)
        self.assertEqual(
            self.client.delete(f"/api/v1/datasets/{self.dataset_id}", headers=headers).status_code, 403
        )
        # Existing read-only Explorer contract stays available to operator tools.
        self.assertEqual(self.client.get("/api/v1/logs/datasets", headers=headers).status_code, 200)

    def test_06_all_mutations_require_valid_csrf(self):
        self.login("admin")
        for headers in ({}, {"X-CSRF-Token": "incorrect"}):
            with self.subTest(headers=bool(headers)):
                self.assertEqual(
                    self.client.post(
                        "/api/v1/datasets",
                        json={"name": "No CSRF", "dataset_key": uuid4().hex},
                        headers=headers,
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.patch(
                        f"/api/v1/datasets/{self.dataset_id}", json={"name": "No CSRF"}, headers=headers
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.delete(f"/api/v1/datasets/{self.dataset_id}", headers=headers).status_code,
                    403,
                )
        self.assertEqual(self.count(Dataset, Dataset.id == self.dataset_id), 1)

    def test_07_duplicate_create_rolls_back_dataset_and_creator_grant(self):
        self.login("manager")
        key = uuid4().hex
        first = self.create(dataset_key=key)
        self.assertEqual(first.status_code, 201, first.json)
        source = self.resource(first)["source_id"]
        before_datasets = self.count(Dataset, Dataset.source_id == source)
        before_grants = self.count(UserDataset, UserDataset.user_id == self.user_id)
        duplicate = self.create(dataset_key=key, name="Duplicate request")
        self.assertEqual(duplicate.status_code, 409, duplicate.json)
        self.assertEqual(self.count(Dataset, Dataset.source_id == source), before_datasets)
        self.assertEqual(self.count(UserDataset, UserDataset.user_id == self.user_id), before_grants)
        self.assertNotIn("INSERT", str(duplicate.json))

    def test_08_personal_source_reused_and_other_users_cannot_attach(self):
        owner = self.login("manager")
        first = self.resource(self.create())
        second = self.resource(self.create())
        self.assertEqual(first["source_id"], second["source_id"])
        with Session(self.engine) as session:
            self.assertEqual(session.get(DataSource, first["source_id"]).source_key, "api-user-" + str(owner))
        self.login("manager", grant=False)
        denied = self.create(source_id=first["source_id"])
        self.assertEqual(denied.status_code, 403, denied.json)
        unknown = self.create(source_id=2**63 - 1)
        self.assertEqual(unknown.status_code, 403, unknown.json)

    def test_09_existing_granted_source_allowed_without_granting_other_datasets(self):
        self.login("manager")
        with Session(self.engine) as session:
            source_id = session.get(Dataset, self.dataset_id).source_id
        created = self.create(source_id=source_id)
        self.assertEqual(created.status_code, 201, created.json)
        self.assertEqual(self.resource(created)["source_id"], source_id)
        self.assertEqual(self.client.get(f"/api/v1/datasets/{self.other_id}").status_code, 403)

    def test_10_invalid_creation_and_mass_assignment(self):
        self.login("admin")
        invalid = [
            [],
            None,
            {},
            {"name": "Only name"},
            {"dataset_key": "only-key"},
            {"name": "", "dataset_key": "key"},
            {"name": "   ", "dataset_key": "key"},
            {"name": "x" * 201, "dataset_key": "key"},
            {"name": "a\x00b", "dataset_key": "key"},
            {"name": "a\nb", "dataset_key": "key"},
            {"name": "\ud800", "dataset_key": "key"},
            {"name": 42, "dataset_key": "key"},
            {"name": "Valid", "dataset_key": "x" * 101},
            {"name": "Valid", "dataset_key": "../path"},
            {"name": "Valid", "dataset_key": True},
            {"name": "Valid", "dataset_key": "key", "source_id": True},
            {"name": "Valid", "dataset_key": "key", "source_id": 0},
            {"name": "Valid", "dataset_key": "key", "data_mode": "trusted"},
            {"name": "Valid", "dataset_key": "key", "state": "imported"},
            {"name": "Valid", "dataset_key": "key", "input_revision": 99},
            {"name": "Valid", "dataset_key": "key", "user_id": self.user_id},
            {"name": "Valid", "dataset_key": "key", "path": "C:/private"},
        ]
        before = self.count(Dataset)
        for body in invalid:
            with self.subTest(case=invalid.index(body)):
                response = self.client.post("/api/v1/datasets", json=body, headers=self.headers())
                self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(self.count(Dataset), before)

    def test_11_immutable_fields_and_invalid_patch_leave_metadata_unchanged(self):
        self.login("admin")
        original = self.resource(self.client.get(f"/api/v1/datasets/{self.dataset_id}"))
        for body in (
            [],
            {},
            {"name": ""},
            {"name": "x" * 201},
            {"name": False},
            {"dataset_key": "changed"},
            {"source_id": 1},
            {"data_mode": "real"},
            {"state": "imported"},
            {"input_revision": 12},
            {"name": "ok", "id": 99},
        ):
            with self.subTest(body_type=type(body).__name__):
                response = self.client.patch(
                    f"/api/v1/datasets/{self.dataset_id}", json=body, headers=self.headers()
                )
                self.assertEqual(response.status_code, 400, response.json)
        current = self.resource(self.client.get(f"/api/v1/datasets/{self.dataset_id}"))
        self.assertEqual(current, original)

    def test_12_bounded_stable_pagination_and_literal_search(self):
        self.login("manager")
        prefix = "page-" + uuid4().hex
        expected = []
        for index in range(3):
            result = self.create(name=prefix + "-" + str(index))
            self.assertEqual(result.status_code, 201, result.json)
            expected.append(self.resource(result)["id"])
        first = self.client.get("/api/v1/datasets", query_string={"q": prefix, "limit": 2})
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(len(first.json["items"]), 2)
        second = self.client.get(
            "/api/v1/datasets",
            query_string={"q": prefix, "limit": 2, "after_id": first.json["next_after_id"]},
        )
        ids = [r["id"] for r in first.json["items"] + second.json["items"]]
        self.assertEqual(ids, expected)
        self.assertIsNone(second.json["next_after_id"])
        literal = self.resource(self.create(name="literal %_ " + uuid4().hex))
        matches = self.client.get("/api/v1/datasets?q=%25_").json["items"]
        self.assertEqual([row["id"] for row in matches], [literal["id"]])
        key_search = "key-search-" + uuid4().hex
        keyed = self.resource(self.create(name="Name deliberately differs", dataset_key=key_search))
        by_key = self.client.get("/api/v1/datasets", query_string={"q": key_search})
        self.assertEqual([row["id"] for row in by_key.json["items"]], [keyed["id"]])
        for args in ({"limit": 0}, {"limit": 101}, {"after_id": -1}, {"after_id": 2**63}, {"q": "x" * 201}):
            self.assertEqual(self.client.get("/api/v1/datasets", query_string=args).status_code, 400)

    def test_13_numeric_path_ids_are_validated_before_sql(self):
        self.login("admin")
        for invalid in (0, 2**63):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.get(f"/api/v1/datasets/{invalid}").status_code, 400)
                self.assertEqual(
                    self.client.patch(
                        f"/api/v1/datasets/{invalid}", json={"name": "x"}, headers=self.headers()
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    self.client.delete(f"/api/v1/datasets/{invalid}", headers=self.headers()).status_code, 400
                )

    def test_14_source_artifact_blocks_delete_without_losing_grants(self):
        self.login("admin")
        with Session(self.engine) as session, session.begin():
            session.add(
                SourceArtifact(
                    dataset_id=self.dataset_id,
                    artifact_key=uuid4().hex,
                    sha256="a" * 64,
                    byte_length=0,
                    parser_version="synthetic-test",
                )
            )
        before_grants = self.count(UserDataset, UserDataset.dataset_id == self.dataset_id)
        result = self.client.delete(f"/api/v1/datasets/{self.dataset_id}", headers=self.headers())
        self.assertEqual(result.status_code, 409, result.json)
        self.assertEqual(self.count(Dataset, Dataset.id == self.dataset_id), 1)
        self.assertEqual(self.count(SourceArtifact, SourceArtifact.dataset_id == self.dataset_id), 1)
        self.assertEqual(self.count(UserDataset, UserDataset.dataset_id == self.dataset_id), before_grants)

    def test_15_completed_or_queued_job_blocks_empty_dataset_deletion(self):
        self.login("admin")
        for state in ("queued", "completed"):
            result = self.create()
            dataset_id = self.resource(result)["id"]
            with Session(self.engine) as session, session.begin():
                job = ProcessingJob(
                    dataset_id=dataset_id, kind="analysis", state=state, job_key=uuid4().hex, configuration={}
                )
                session.add(job)
                session.flush()
                job_id = job.id
            try:
                denied = self.client.delete(f"/api/v1/datasets/{dataset_id}", headers=self.headers())
                self.assertEqual(denied.status_code, 409, denied.json)
                self.assertEqual(self.count(ProcessingJob, ProcessingJob.dataset_id == dataset_id), 1)
            finally:
                # Retain the fixture, but do not leave work for another test's
                # global queue worker to consume after this assertion finishes.
                if state == "queued":
                    with Session(self.engine) as session, session.begin():
                        owned_job = session.get(ProcessingJob, job_id)
                        if owned_job.state == "queued":
                            owned_job.state = "failed"
                            owned_job.error_code = "completed_test_fixture"

    def test_16_coverage_child_blocks_deletion(self):
        self.login("admin")
        with Session(self.engine) as session, session.begin():
            session.add(
                CoverageInterval(
                    dataset_id=self.dataset_id,
                    layer="ingestion",
                    state="unknown",
                    start_time=baseline.NOW,
                    end_time=baseline.NOW + timedelta(minutes=1),
                )
            )
        result = self.client.delete(f"/api/v1/datasets/{self.dataset_id}", headers=self.headers())
        self.assertEqual(result.status_code, 409, result.json)

    def test_17_nonpristine_revision_or_busy_state_blocks_deletion(self):
        self.login("admin")
        for values in ({"input_revision": 1}, {"state": "importing"}, {"state": "partial"}):
            item = self.resource(self.create())
            with Session(self.engine) as session, session.begin():
                dataset = session.get(Dataset, item["id"])
                for key, value in values.items():
                    setattr(dataset, key, value)
            denied = self.client.delete(f"/api/v1/datasets/{item['id']}", headers=self.headers())
            self.assertEqual(denied.status_code, 409, denied.json)

    def test_18_failure_after_acl_delete_rolls_back_parent_and_all_grants(self):
        self.login("admin")
        item = self.resource(self.create())
        dataset_id = item["id"]
        with Session(self.engine) as session, session.begin():
            viewer = User(username=uuid4().hex, password_hash="synthetic-unused", role="viewer")
            session.add(viewer)
            session.flush()
            session.add(UserDataset(user_id=viewer.id, dataset_id=dataset_id))
        before_grants = self.count(UserDataset, UserDataset.dataset_id == dataset_id)
        operations = []

        def fail_parent(connection, cursor, statement, params, context, many):
            sql = " ".join(statement.replace("`", "").upper().split())
            if sql.startswith("DELETE FROM USER_DATASETS"):
                operations.append("delete_grants")
            elif sql.startswith("DELETE FROM DATASETS"):
                operations.append("delete_parent")
                raise OperationalError(
                    "Synthetic deletion failure",
                    {},
                    RuntimeError("owned rollback injection"),
                    hide_parameters=True,
                )

        event.listen(self.engine, "before_cursor_execute", fail_parent)
        try:
            result = self.client.delete(f"/api/v1/datasets/{dataset_id}", headers=self.headers())
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_parent)
        self.assertEqual(result.status_code, 503, result.json)
        self.assertEqual(operations, ["delete_grants", "delete_parent"])
        self.assertEqual(self.count(Dataset, Dataset.id == dataset_id), 1)
        self.assertEqual(self.count(UserDataset, UserDataset.dataset_id == dataset_id), before_grants)
        self.assertNotIn("owned rollback injection", str(result.json))

    def test_19_table_delete_privileges_do_not_allow_raw_log_deletion(self):
        with self.assertRaises(OperationalError):
            with self.engine.begin() as connection:
                connection.execute(text("DELETE FROM log_events WHERE id=-1"))

    def test_20_existing_log_explorer_metadata_stays_compatible(self):
        self.login("manager")
        item = self.resource(self.create(name="New visible dataset"))
        response = self.client.get("/api/v1/logs/datasets")
        self.assertEqual(response.status_code, 200, response.json)
        visible = {d["id"]: d for d in response.json["datasets"]}
        self.assertIn(item["id"], visible)
        self.assertEqual(visible[item["id"]]["name"], item["name"])
        self.assertEqual(visible[item["id"]]["data_mode"], "unverified")
        self.assertNotIn(self.other_id, visible)

    def test_21_creator_grant_failure_rolls_back_source_and_dataset(self):
        self.login("admin", grant=False)
        key = uuid4().hex
        before_sources = self.count(DataSource)
        before_datasets = self.count(Dataset)

        def fail_membership(connection, cursor, statement, params, context, many):
            sql = " ".join(statement.replace("`", "").upper().split())
            if sql.startswith("INSERT INTO USER_DATASETS"):
                raise OperationalError(
                    "Synthetic grant failure",
                    {},
                    RuntimeError("owned create rollback injection"),
                    hide_parameters=True,
                )

        event.listen(self.engine, "before_cursor_execute", fail_membership)
        try:
            response = self.create(dataset_key=key)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_membership)
        self.assertEqual(response.status_code, 503, response.json)
        self.assertEqual(self.count(DataSource), before_sources)
        self.assertEqual(self.count(Dataset), before_datasets)
        self.assertEqual(self.count(UserDataset, UserDataset.user_id == self.user_id), 0)
        self.assertNotIn("owned create rollback injection", str(response.json))

    def test_22_revoked_grant_is_not_retained_by_an_admin_session(self):
        self.login("admin")
        self.assertEqual(self.client.get(f"/api/v1/datasets/{self.dataset_id}").status_code, 200)
        with Session(self.engine) as session, session.begin():
            session.execute(
                delete(UserDataset).where(
                    UserDataset.user_id == self.user_id,
                    UserDataset.dataset_id == self.dataset_id,
                )
            )
        self.assertEqual(self.client.get("/api/v1/datasets").json["items"], [])
        self.assertEqual(self.client.get(f"/api/v1/datasets/{self.dataset_id}").status_code, 403)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/datasets/{self.dataset_id}", json={"name": "Not granted"}, headers=self.headers()
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/datasets/{self.dataset_id}", headers=self.headers()).status_code, 403
        )

    def test_23_concurrent_first_registrations_share_one_personal_source(self):
        actor_id = self.login("manager")
        cookie_name = self.app.config.get("SESSION_COOKIE_NAME", "session")
        cookie = self.client.get_cookie(cookie_name)
        self.assertIsNotNone(cookie)
        csrf = self.headers()
        barrier = Barrier(2, timeout=5)
        started = []

        def synchronize_first_source(connection, cursor, statement, params, context, many):
            sql = " ".join(statement.replace("`", "").upper().split())
            if sql.startswith("INSERT INTO DATA_SOURCES"):
                # Both authenticated requests have already established their
                # repeatable-read snapshots before either personal-source upsert.
                started.append(True)
                barrier.wait()

        def register(key):
            client = self.app.test_client()
            client.set_cookie(cookie_name, cookie.value)
            response = client.post(
                "/api/v1/datasets",
                json={
                    "name": "Concurrent owned metadata",
                    "dataset_key": key,
                },
                headers=csrf,
            )
            return response.status_code, response.json

        keys = [uuid4().hex, uuid4().hex]
        event.listen(self.engine, "before_cursor_execute", synchronize_first_source)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(register, key) for key in keys]
                results = [future.result(timeout=12) for future in futures]
        finally:
            event.remove(self.engine, "before_cursor_execute", synchronize_first_source)
        self.assertEqual(len(started), 2)
        self.assertEqual([code for code, _ in results], [201, 201], results)
        items = [body["dataset"] for _, body in results]
        ids = {item["id"] for item in items}
        self.assertEqual(len(ids), 2)
        self.assertEqual(len({item["source_id"] for item in items}), 1)
        self.assertEqual({item["dataset_key"] for item in items}, set(keys))
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(DataSource)
                    .where(DataSource.source_key == "api-user-" + str(actor_id))
                ),
                1,
            )
            grants = set(
                session.scalars(select(UserDataset.dataset_id).where(UserDataset.user_id == actor_id))
            )
        self.assertEqual(grants, ids | {self.dataset_id})
        self.assertNotIn(self.other_id, grants)


if __name__ == "__main__":
    unittest.main()
