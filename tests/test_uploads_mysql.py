"""Real MySQL upload/form/worker/security tests on retained isolated fixtures.

Original uploaded files remain in owned .local test storage. Only this test's
queued/running upload jobs are marked failed on teardown, avoiding queue leaks.
"""

import csv
import hashlib
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session
import test_dataset_crud_mysql as crud
import test_mysql_integration as baseline
from werkzeug.datastructures import MultiDict

from app.models import Dataset, GroundTruthLabel, LogEvent, ProcessingJob, RawLogRecord, SourceArtifact
from app.services.bgl_ingestion import import_lease
import app.services.uploads as uploads
from app.services.uploads import TYPE, run_once

LINE = baseline.LINE


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Upload MySQL integration NOT RUN (explicit opt-in required)",
)
class UploadMySQLTests(unittest.TestCase):
    setUpClass = classmethod(crud.DatasetCRUDMySQLTests.setUpClass.__func__)
    login = crud.DatasetCRUDMySQLTests.login
    headers = crud.DatasetCRUDMySQLTests.headers
    count = crud.DatasetCRUDMySQLTests.count

    def setUp(self):
        baseline.MySQLIntegrationTests.setUp(self)
        from app.security import attempts

        attempts.clear()
        self.app.config.update(SECRET_KEY="synthetic-upload-session-secret", WTF_CSRF_ENABLED=True)
        self.client = self.app.test_client()
        self.storage = Path(".local/test-upload-" + uuid4().hex).resolve()
        self.storage.mkdir(parents=True, mode=0o700)
        self.storage_patch = patch("app.services.uploads.UPLOAD_ROOT", self.storage)
        self.storage_patch.start()

    def tearDown(self):
        # Do not leave this test's accepted-but-unprocessed fixtures ahead of the
        # next test in the shared queue. Preserve all rows/files for inspection.
        with Session(self.engine) as session, session.begin():
            for job in session.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.dataset_id == self.dataset_id,
                    ProcessingJob.kind == "parsing",
                    ProcessingJob.state.in_(["queued", "running"]),
                    ProcessingJob.configuration["type"].as_string() == TYPE,
                )
            ):
                job.state, job.error_code = "failed", "fixture_retained"
        self.storage_patch.stop()
        self.session.close()

    def signed_csrf(self):
        response = self.client.get("/api/v1/forms/csrf")
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["csrf_token"]

    def upload(
        self, content=LINE, name="source.log", *, key=None, dataset=None, signed=True, header=True, extra=None
    ):
        fields = {
            "dataset_id": str(self.dataset_id if dataset is None else dataset),
            "idempotency_key": key or uuid4().hex,
            "file": (io.BytesIO(content), name),
        }
        if signed:
            fields["csrf_token"] = self.signed_csrf()
        fields.update(extra or {})
        return self.client.post(
            "/api/v1/uploads",
            data=fields,
            content_type="multipart/form-data",
            headers=self.headers() if header else {},
        )

    def status(self, response):
        return self.client.get(response.json["status_url"])

    def test_01_queue_then_worker_preserves_actual_bytes_labels_and_provenance(self):
        self.login("analyst")
        original = LINE.replace(b"\n", b"\r\n") + LINE.rstrip(b"\n")
        response = self.upload(original)
        self.assertEqual(response.status_code, 202, response.json)
        self.assertEqual(response.json["state"], "queued")
        self.assertEqual(self.count(LogEvent, LogEvent.dataset_id == self.dataset_id), 0)
        self.assertTrue(run_once(self.engine))
        result = self.status(response)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(
            (result.json["state"], result.json["processed_count"], result.json["parsed_events"]),
            ("completed", 2, 2),
        )
        self.assertNotEqual(result.json["job_id"], result.json["child_import_job_id"])
        self.assertEqual(result.json["original_sha256"], hashlib.sha256(original).hexdigest())
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RawLogRecord)
                .where(RawLogRecord.dataset_id == self.dataset_id)
                .order_by(RawLogRecord.line_number)
            ).all()
            self.assertEqual(b"".join(row.raw_bytes for row in rows), original)
            self.assertEqual([row.byte_offset for row in rows], [0, len(LINE) + 1])
            labels = session.execute(
                select(GroundTruthLabel.source, GroundTruthLabel.version, GroundTruthLabel.label).where(
                    GroundTruthLabel.dataset_id == self.dataset_id
                )
            ).all()
            self.assertEqual(labels, [("uploaded-bgl", "supplied", "-"), ("uploaded-bgl", "supplied", "-")])
            event = session.scalar(
                select(LogEvent).where(LogEvent.dataset_id == self.dataset_id).order_by(LogEvent.id)
            )
            self.assertEqual(
                event.attributes["upload"]["original_sha256"], hashlib.sha256(original).hexdigest()
            )
            self.assertEqual(event.attributes["upload"]["original_byte_offset"], 0)
            outer = session.get(ProcessingJob, result.json["job_id"])
            inner = session.get(ProcessingJob, result.json["child_import_job_id"])
            self.assertEqual(
                (outer.kind, inner.kind, outer.state, inner.state),
                ("parsing", "ingestion", "completed", "completed"),
            )

    def test_02_csv_records_link_to_original_container_rows_not_fake_offsets(self):
        self.login("analyst")
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["raw_line"])
        writer.writerow([LINE.decode().rstrip("\n")])
        writer.writerow([LINE.decode()])
        original = stream.getvalue().encode()
        response = self.upload(original, "supplied.csv")
        self.assertEqual(response.status_code, 202, response.json)
        self.assertTrue(run_once(self.engine))
        self.assertEqual(self.status(response).json["state"], "completed")
        with Session(self.engine) as session:
            events = session.scalars(
                select(LogEvent).where(LogEvent.dataset_id == self.dataset_id).order_by(LogEvent.id)
            ).all()
            self.assertEqual([e.attributes["upload"]["csv_row"] for e in events], [2, 3])
            self.assertEqual([e.attributes["upload"]["bgl_byte_offset"] for e in events], [0, len(LINE)])
            self.assertNotIn("original_byte_offset", events[0].attributes["upload"])
            self.assertEqual(
                events[0].attributes["upload"]["original_sha256"], hashlib.sha256(original).hexdigest()
            )
            rows = session.scalars(
                select(RawLogRecord)
                .where(RawLogRecord.dataset_id == self.dataset_id)
                .order_by(RawLogRecord.id)
            ).all()
            self.assertEqual(b"".join(row.raw_bytes for row in rows), LINE + LINE)
        original_path = self.storage / response.json["upload_id"] / "original.csv"
        self.assertEqual(original_path.read_bytes(), original)

    def test_03_rbac_grants_and_both_csrf_layers(self):
        self.assertEqual(self.client.post("/api/v1/uploads").status_code, 403)
        self.login("viewer")
        self.assertEqual(self.upload().status_code, 403)
        self.login("analyst")
        self.assertEqual(self.upload(header=False).status_code, 403)
        missing = self.upload(signed=False)
        self.assertEqual(missing.status_code, 400, missing.json)
        self.assertIn("csrf_token", missing.json["error"]["fields"])
        self.assertEqual(self.upload(dataset=self.other_id).status_code, 403)
        response = self.upload()
        self.assertEqual(response.status_code, 202, response.json)
        url = response.json["status_url"]
        self.login("admin", grant=False)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url + "/retry", headers=self.headers()).status_code, 403)
        self.assertEqual(self.upload().status_code, 403)

    def test_04_idempotent_replay_and_conflict_do_not_duplicate_files_or_rows(self):
        self.login("analyst")
        key = "same-key-" + uuid4().hex
        first = self.upload(key=key)
        self.assertEqual(first.status_code, 202, first.json)
        second = self.upload(key=key)
        self.assertEqual(second.status_code, 200, second.json)
        self.assertEqual(second.json["upload_id"], first.json["upload_id"])
        self.assertEqual(len(list(self.storage.iterdir())), 1)
        changed = self.upload(LINE + LINE, key=key)
        self.assertEqual(changed.status_code, 409, changed.json)
        self.assertEqual(changed.json["error"]["code"], "idempotency_conflict")
        self.assertEqual(len(list(self.storage.iterdir())), 1)
        self.assertTrue(run_once(self.engine))
        again = self.upload(key=key)
        self.assertEqual((again.status_code, again.json["state"]), (200, "completed"))
        self.assertEqual(self.count(LogEvent, LogEvent.dataset_id == self.dataset_id), 1)
        self.assertFalse(run_once(self.engine))

    def test_05_malformed_rows_are_retained_without_invented_events(self):
        self.login("analyst")
        response = self.upload(LINE + b"not a BGL row\n")
        self.assertEqual(response.status_code, 202, response.json)
        self.assertTrue(run_once(self.engine))
        result = self.status(response).json
        self.assertEqual(
            (result["processed_count"], result["parsed_events"], result["malformed_rows"]), (2, 1, 1)
        )
        with Session(self.engine) as session:
            raw = session.scalars(
                select(RawLogRecord)
                .where(RawLogRecord.dataset_id == self.dataset_id)
                .order_by(RawLogRecord.line_number)
            ).all()
            self.assertEqual(raw[1].parse_error, "invalid_field_count")
        self.assertEqual(self.count(GroundTruthLabel, GroundTruthLabel.dataset_id == self.dataset_id), 1)

    def test_06_invalid_files_and_parameter_pollution_create_no_job(self):
        self.login("analyst")
        for body, name in (
            (b"\x00" + LINE, "binary.log"),
            (b"\xff" + LINE, "bad.txt"),
            (b"\xef\xbb\xbf" + LINE, "bom.txt"),
            (b"plain unrelated text", "other.log"),
            (b"timestamp,message\n1,hello\n", "bad.csv"),
            (LINE, "../escape.log"),
        ):
            with self.subTest(name=name):
                self.assertIn(self.upload(body, name).status_code, (400, 415, 422))
        self.assertEqual(self.upload(extra={"server_path": "/private"}).status_code, 400)
        fields = MultiDict(
            [
                ("dataset_id", str(self.dataset_id)),
                ("dataset_id", str(self.other_id)),
                ("idempotency_key", "duplicate"),
                ("csrf_token", self.signed_csrf()),
                ("file", (io.BytesIO(LINE), "input.log")),
            ]
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/uploads", data=fields, content_type="multipart/form-data", headers=self.headers()
            ).status_code,
            400,
        )
        for body in ([], ["not", "multipart"], {"server_path": "C:/private"}):
            self.assertEqual(
                self.client.post("/api/v1/uploads", json=body, headers=self.headers()).status_code, 400
            )
        self.assertEqual(self.count(ProcessingJob, ProcessingJob.dataset_id == self.dataset_id), 0)
        self.assertEqual(list(self.storage.iterdir()), [])

    def test_07_request_and_file_caps_do_not_change_other_endpoint_limit(self):
        self.login("analyst")
        valid_large = LINE * ((1024 * 1024 // len(LINE)) + 20)
        accepted = self.upload(valid_large, "over-one-mib.log")
        self.assertEqual(accepted.status_code, 202, accepted.json)
        self.assertGreater(accepted.json["provenance"]["original_bytes"], 1024 * 1024)
        too_large = self.client.post(
            "/api/v1/uploads",
            data=b"x" * (17 * 1024 * 1024 + 1),
            content_type="multipart/form-data; boundary=unused",
            headers=self.headers(),
        )
        self.assertEqual(too_large.status_code, 413, too_large.json)
        login_large = self.client.post(
            "/api/v1/auth/login", data=b"x" * (1024 * 1024 + 1), content_type="application/json"
        )
        self.assertEqual(login_large.status_code, 413)

    def test_08_original_file_bytes_are_not_exposed_by_an_http_download(self):
        self.login("analyst")
        response = self.upload(LINE.replace(b"example", b"password=synthetic-secret"))
        self.assertEqual(response.status_code, 202, response.json)
        self.assertEqual(self.client.get(response.json["status_url"] + "/original").status_code, 404)
        self.assertNotIn("synthetic-secret", self.status(response).text)
        for identity in ("../escape", "a" * 31, "G" * 32):
            self.assertEqual(self.client.get("/api/v1/uploads/" + identity).status_code, 404)

    def test_09_retry_blocks_active_lease_and_enforces_attempt_limit(self):
        self.login("analyst")
        response = self.upload()
        job_id, url = response.json["job_id"], response.json["status_url"]
        with Session(self.engine) as session, session.begin():
            session.get(ProcessingJob, job_id).state = "running"
        with import_lease(self.engine, "upload-job:" + str(job_id)):
            denied = self.client.post(url + "/retry", headers=self.headers())
            self.assertEqual(denied.status_code, 409, denied.json)
            self.assertEqual(denied.json["error"]["code"], "worker_active")
        allowed = self.client.post(url + "/retry", headers=self.headers())
        self.assertEqual((allowed.status_code, allowed.json["state"]), (202, "queued"))
        with Session(self.engine) as session, session.begin():
            job = session.get(ProcessingJob, job_id)
            job.state, job.result = "failed", {"attempts": 3}
        self.assertEqual(self.client.post(url + "/retry", headers=self.headers()).status_code, 409)

    def test_10_rollback_committed_progress_and_resume_have_no_duplicate_lines(self):
        self.login("analyst")
        original = LINE * 1200
        response = self.upload(original)
        self.assertEqual(response.status_code, 202, response.json)
        real_ingest = uploads.ingest_bgl
        committed = []

        def interrupted(*args, **kwargs):
            callback = kwargs["progress"]

            def observed(value):
                with Session(self.engine) as session:
                    checkpoint = session.scalar(
                        select(SourceArtifact.checkpoint_line).where(
                            SourceArtifact.dataset_id == self.dataset_id
                        )
                    )
                    rows = session.scalar(
                        select(func.count())
                        .select_from(RawLogRecord)
                        .where(RawLogRecord.dataset_id == self.dataset_id)
                    )
                self.assertEqual(checkpoint, rows)
                self.assertEqual(checkpoint, value["line"])
                committed.append(value["line"])
                callback(value)

            def fail(line):
                if line >= 1000:
                    raise RuntimeError("Synthetic failure before second batch commit")

            return real_ingest(*args, **dict(kwargs, before_commit=fail, progress=observed))

        with patch("app.services.uploads.ingest_bgl", side_effect=interrupted):
            self.assertTrue(run_once(self.engine))
        failed = self.status(response).json
        self.assertEqual((failed["state"], failed["processed_count"]), ("failed", 500))
        self.assertEqual(failed["error_code"], "upload_ingestion_failed")
        self.assertEqual(committed, [500])
        self.assertEqual(
            self.client.post(response.json["status_url"] + "/retry", headers=self.headers()).status_code, 202
        )
        self.assertTrue(run_once(self.engine))
        completed = self.status(response).json
        self.assertEqual(
            (completed["state"], completed["processed_count"], completed["attempts"]), ("completed", 1200, 2)
        )
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RawLogRecord)
                .where(RawLogRecord.dataset_id == self.dataset_id)
                .order_by(RawLogRecord.line_number)
            ).all()
            self.assertEqual(len(rows), len({r.line_number for r in rows}))
            self.assertEqual(b"".join(r.raw_bytes for r in rows), original)
        self.assertEqual(self.count(LogEvent, LogEvent.dataset_id == self.dataset_id), 1200)
        self.assertEqual(self.count(GroundTruthLabel, GroundTruthLabel.dataset_id == self.dataset_id), 1200)

    def test_11_mutated_artifacts_fail_before_import_and_cannot_retry(self):
        self.login("analyst")
        for filename in ("original.log", "normalized.zip"):
            with self.subTest(filename=filename):
                response = self.upload(key="mutation-" + filename)
                self.assertEqual(response.status_code, 202, response.json)
                artifact = self.storage / response.json["upload_id"] / filename
                with artifact.open("ab") as output:
                    output.write(b"changed")
                self.assertTrue(run_once(self.engine))
                status = self.status(response).json
                self.assertEqual(
                    (status["state"], status["error_code"], status["can_retry"]),
                    ("failed", "upload_integrity", False),
                )
                self.assertEqual(
                    self.client.post(
                        response.json["status_url"] + "/retry", headers=self.headers()
                    ).status_code,
                    409,
                )
        self.assertEqual(self.count(LogEvent, LogEvent.dataset_id == self.dataset_id), 0)

    def test_12_upload_job_prevents_metadata_deletion_without_deleting_bytes(self):
        self.login("admin")
        response = self.upload()
        self.assertEqual(response.status_code, 202, response.json)
        denied = self.client.delete("/api/v1/datasets/" + str(self.dataset_id), headers=self.headers())
        self.assertEqual((denied.status_code, denied.json["error"]["code"]), (409, "dataset_not_empty"))
        self.assertTrue((self.storage / response.json["upload_id"] / "original.log").exists())
        self.assertEqual(self.count(Dataset, Dataset.id == self.dataset_id), 1)


if __name__ == "__main__":
    unittest.main()
