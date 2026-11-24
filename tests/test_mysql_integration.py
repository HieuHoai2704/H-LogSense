"""Real MySQL only. Requires a fresh token-marked, uniquely named test schema."""

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unittest
from uuid import uuid4
from zipfile import ZipFile

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import (
    AnomalyOutput,
    CoverageInterval,
    Dataset,
    DataSource,
    DetectionUnit,
    Detector,
    DetectorRun,
    DetectorVersion,
    GroundTruthLabel,
    LogEvent,
    ProcessingJob,
    RawLogRecord,
    SourceArtifact,
    UnitEvent,
)
from app.repositories import archive_dataset, page_events
from app.services.bgl_ingestion import ingest_bgl
from app.services.detection import detect

LINE = b"- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 R02-M1-N0-C:J12-U11 RAS KERNEL INFO example\n"
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def assert_isolated(app):
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if (
        url.drivername != "mysql+pymysql"
        or not re.fullmatch(r"logsense_test_[0-9a-f]{12}", url.database or "")
        or not os.environ.get("LOGSENSE_TEST_TOKEN")
    ):
        raise RuntimeError("Refusing integration tests without an isolated test schema and token.")
    with app.app_context(), db.engine.connect() as connection:
        token = connection.execute(text("SELECT token_hash FROM logsense_test_guard")).scalar_one()
        if token != hashlib.sha256(os.environ["LOGSENSE_TEST_TOKEN"].encode()).hexdigest():
            raise RuntimeError("Test schema ownership check failed.")


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "MySQL integration NOT RUN (explicit opt-in required)",
)
class MySQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({"TESTING": True})
        assert_isolated(cls.app)
        with cls.app.app_context():
            upgrade()
            cls.engine = db.engine

    def setUp(self):
        self.session = Session(self.engine)
        with self.session.begin():
            source = DataSource(source_key=uuid4().hex, name="Integration fixture")
            self.session.add(source)
            self.session.flush()
            dataset = Dataset(
                source_id=source.id,
                dataset_key=uuid4().hex,
                name="Synthetic integration fixture",
                data_mode="synthetic",
            )
            other = Dataset(
                source_id=source.id,
                dataset_key=uuid4().hex,
                name="Isolated second fixture",
                data_mode="synthetic",
            )
            self.session.add_all([dataset, other])
            self.session.flush()
            self.dataset_id, self.other_id = dataset.id, other.id
        self.session.close()

    def tearDown(self):
        self.session.close()

    def event(self, session, *, timestamp=NOW):
        artifact = SourceArtifact(
            dataset_id=self.dataset_id,
            artifact_key=uuid4().hex,
            sha256="a" * 64,
            byte_length=len(LINE),
            parser_version="test",
        )
        session.add(artifact)
        session.flush()
        raw = RawLogRecord(
            dataset_id=self.dataset_id,
            artifact_id=artifact.id,
            line_number=1,
            byte_offset=0,
            raw_bytes=LINE,
        )
        session.add(raw)
        session.flush()
        event = LogEvent(
            dataset_id=self.dataset_id,
            raw_id=raw.id,
            parser_version="test",
            timestamp=timestamp,
            raw_timestamp="original",
            message="example",
            attributes={"unicode": "Viá»‡t Nam", "list": [1, 2]},
        )
        session.add(event)
        session.flush()
        return event

    def unit(self, session, event):
        unit = DetectionUnit(
            dataset_id=self.dataset_id,
            unit_key=uuid4().hex,
            kind="event",
            event_id=event.id,
            start_time=event.timestamp,
        )
        session.add(unit)
        session.flush()
        return unit

    def make_run(self, session):
        detector = Detector(detector_key=uuid4().hex, family="rule")
        session.add(detector)
        session.flush()
        version = DetectorVersion(detector_id=detector.id, version="1", configuration={"threshold": 1})
        session.add(version)
        session.flush()
        run = DetectorRun(
            dataset_id=self.dataset_id,
            detector_id=detector.id,
            version_id=version.id,
            run_key=uuid4().hex,
            state="completed",
            input_revision=0,
            configuration={},
        )
        session.add(run)
        session.flush()
        return run

    def test_01_connectivity_and_utc(self):
        with self.engine.connect() as connection:
            version, zone = connection.execute(text("SELECT VERSION(), @@time_zone")).one()
            self.assertTrue(version.startswith("8."))
            self.assertEqual(zone, "+00:00")
        self.assertEqual(self.app.test_client().get("/api/v1/health/database").status_code, 200)

    def test_02_migration_schema_matches_models(self):
        with self.engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "include_object": lambda obj, name, kind, reflected, compare: (
                        name != "logsense_test_guard"
                    ),
                },
            )
            diff = compare_metadata(context, db.metadata)
            self.assertEqual(diff, [])
            self.assertEqual(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one(),
                "0006",
            )
            tables = inspect(connection).get_table_names()
            self.assertTrue(set(db.metadata.tables) <= set(tables))

    def test_03_dataset_archive_relationship(self):
        with self.session.begin():
            archive_dataset(self.session, self.dataset_id)
            self.assertEqual(self.session.get(Dataset, self.dataset_id).state, "archived")
            self.assertIsNotNone(self.session.get(Dataset, self.dataset_id).source)

    def test_04_raw_bytes_exact_and_json_roundtrip(self):
        with self.session.begin():
            event = self.event(self.session)
            raw = self.session.get(RawLogRecord, event.raw_id)
            self.session.expire_all()
            self.assertEqual(raw.raw_bytes, LINE)
            self.assertEqual(event.attributes, {"unicode": "Viá»‡t Nam", "list": [1, 2]})

    def test_05_half_open_range_and_keyset_ties(self):
        with self.session.begin():
            first = self.event(self.session)
            second = self.event(self.session)
            self.event(self.session, timestamp=NOW + timedelta(seconds=1))
            page = page_events(self.session, self.dataset_id, NOW, NOW + timedelta(seconds=1), limit=1)
            self.assertEqual([e.id for e in page], [first.id])
            page = page_events(
                self.session,
                self.dataset_id,
                NOW,
                NOW + timedelta(seconds=1),
                cursor=(first.timestamp, first.id),
                limit=1,
            )
            self.assertEqual([e.id for e in page], [second.id])
            self.assertEqual(
                page_events(self.session, self.other_id, NOW, NOW + timedelta(seconds=1)),
                [],
            )

    def test_06_cross_dataset_raw_fk_rejected(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            event = self.event(self.session)
            self.session.add(
                LogEvent(
                    dataset_id=self.other_id,
                    raw_id=event.raw_id,
                    parser_version="cross",
                    timestamp=NOW,
                    raw_timestamp="original",
                    message="x",
                    attributes={},
                )
            )
            self.session.flush()

    def test_07_cross_dataset_membership_rejected(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            event = self.event(self.session)
            unit = DetectionUnit(
                dataset_id=self.other_id,
                unit_key="foreign",
                kind="session",
                start_time=NOW,
            )
            self.session.add(unit)
            self.session.flush()
            self.session.add(UnitEvent(dataset_id=self.other_id, unit_id=unit.id, event_id=event.id))
            self.session.flush()

    def test_08_cross_dataset_anomaly_run_rejected(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            event = self.event(self.session)
            unit = self.unit(self.session, event)
            run = self.make_run(self.session)
            self.session.add(
                AnomalyOutput(
                    dataset_id=self.other_id,
                    unit_id=unit.id,
                    run_id=run.id,
                    anchor_time=NOW,
                    score=-0.6,
                    evidence={},
                )
            )
            self.session.flush()

    def test_09_version_mapping_enforced(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            run = self.make_run(self.session)
            other = Detector(detector_key=uuid4().hex, family="rule")
            self.session.add(other)
            self.session.flush()
            run.detector_id = other.id
            self.session.flush()

    def test_10_negative_score_not_probability(self):
        with self.session.begin():
            unit = self.unit(self.session, self.event(self.session))
            run = self.make_run(self.session)
            anomaly = AnomalyOutput(
                dataset_id=self.dataset_id,
                unit_id=unit.id,
                run_id=run.id,
                anchor_time=NOW,
                score=-0.71,
                evidence={"threshold": -0.5},
            )
            self.session.add(anomaly)
            self.session.flush()
            self.session.expire(anomaly)
            self.assertEqual(anomaly.score, -0.71)

    def test_11_duplicates_rejected(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            event = self.event(self.session)
            self.session.add(
                LogEvent(
                    dataset_id=self.dataset_id,
                    raw_id=event.raw_id,
                    parser_version="test",
                    timestamp=NOW,
                    raw_timestamp="original",
                    message="x",
                    attributes={},
                )
            )
            self.session.flush()

    def test_12_rollback_restores_counts(self):
        with self.assertRaises(RuntimeError), self.session.begin():
            self.event(self.session)
            raise RuntimeError("Injected failure")
        with self.session.begin():
            count = self.session.scalar(
                select(func.count()).select_from(LogEvent).where(LogEvent.dataset_id == self.dataset_id)
            )
            self.assertEqual(count, 0)

    def test_13_coverage_unknown_and_proof(self):
        with self.assertRaises(OperationalError) as failure, self.session.begin():
            self.session.add(
                CoverageInterval(
                    dataset_id=self.dataset_id,
                    layer="parsing",
                    state="complete",
                    start_time=NOW,
                    end_time=NOW + timedelta(seconds=1),
                )
            )
            self.session.flush()
        self.assertEqual(failure.exception.orig.args[0], 3819)
        with self.session.begin():
            self.assertEqual(
                self.session.scalar(
                    select(func.count())
                    .select_from(CoverageInterval)
                    .where(CoverageInterval.dataset_id == self.dataset_id)
                ),
                0,
            )

    def test_14_unit_interval_boundary_enforced(self):
        with self.assertRaises(OperationalError) as failure, self.session.begin():
            self.session.add(
                DetectionUnit(
                    dataset_id=self.dataset_id,
                    unit_key="invalid",
                    kind="window",
                    start_time=NOW,
                    end_time=NOW,
                )
            )
            self.session.flush()
        self.assertEqual(failure.exception.orig.args[0], 3819)

    def test_15_ground_truth_accepts_session_without_fake_event(self):
        with self.session.begin():
            unit = DetectionUnit(
                dataset_id=self.dataset_id,
                unit_key="block",
                kind="block",
                start_time=NOW,
            )
            self.session.add(unit)
            self.session.flush()
            label = GroundTruthLabel(
                dataset_id=self.dataset_id,
                unit_id=unit.id,
                source="test",
                version="1",
                label="anomalous",
            )
            self.session.add(label)
            self.session.flush()
            self.assertIsNone(label.event_id)

    def zipped(self, content):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.zip"
        with ZipFile(path, "w") as z:
            z.writestr("BGL.log", content)
        return path

    def test_16_ingestion_resume_idempotency_and_malformed(self):
        path = self.zipped(LINE + b"bad row\n" + LINE.replace(b"INFO", b"ERROR"))
        first = ingest_bgl(self.engine, self.dataset_id, path, limit=1, batch_size=1)
        self.assertEqual(first["physical_lines"], 1)
        full = ingest_bgl(self.engine, self.dataset_id, path, batch_size=1)
        self.assertEqual(
            (full["physical_lines"], full["parsed_events"], full["malformed_rows"]),
            (3, 2, 1),
        )
        self.assertEqual(ingest_bgl(self.engine, self.dataset_id, path), full)
        with self.session.begin():
            self.assertEqual(
                self.session.scalar(
                    select(func.count())
                    .select_from(RawLogRecord)
                    .where(RawLogRecord.dataset_id == self.dataset_id)
                ),
                3,
            )

    def test_17_batch_failure_and_resume(self):
        path = self.zipped(LINE * 4)

        def fail(line):
            if line == 4:
                raise RuntimeError("Injected batch failure")

        with self.assertRaises(RuntimeError):
            ingest_bgl(self.engine, self.dataset_id, path, batch_size=2, before_commit=fail)
        with self.session.begin():
            artifact = self.session.scalar(
                select(SourceArtifact).where(SourceArtifact.dataset_id == self.dataset_id)
            )
            self.assertEqual((artifact.checkpoint_line, artifact.parsed_count), (2, 2))
            self.assertEqual(
                self.session.scalar(
                    select(func.count()).select_from(LogEvent).where(LogEvent.dataset_id == self.dataset_id)
                ),
                2,
            )
        self.assertEqual(
            ingest_bgl(self.engine, self.dataset_id, path, batch_size=2)["parsed_events"],
            4,
        )

    def test_18_changed_source_resume_rejected(self):
        path = self.zipped(LINE)
        ingest_bgl(self.engine, self.dataset_id, path)
        with ZipFile(path, "w") as zipped:
            zipped.writestr("BGL.log", LINE * 2)
        with self.assertRaises(ValueError):
            ingest_bgl(self.engine, self.dataset_id, path)

    def test_19_rule_detector_persistence_and_private_api(self):
        path = self.zipped(LINE + LINE.replace(b"INFO", b"ERROR"))
        ingest_bgl(self.engine, self.dataset_id, path)
        result = detect(self.engine, self.dataset_id)
        self.assertEqual((result["evaluated_units"], result["anomaly_outputs"]), (2, 1))
        self.app.config.update(
            DATABASE_READ_TOKEN="synthetic-test-token",
            DATABASE_ALLOWED_DATASETS=(self.dataset_id,),
        )
        client = self.app.test_client()
        url = f"/api/v1/database/anomalies?dataset_id={self.dataset_id}&run_id={result['run_id']}"
        self.assertEqual(client.get(url).status_code, 403)
        response = client.get(url, headers={"Authorization": "Bearer synthetic-test-token"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["score_is_probability"])
        self.assertEqual(len(response.json["anomalies"]), 1)
        anomaly_id = response.json["anomalies"][0]["id"]
        evidence_url = f"/api/v1/database/anomalies/{anomaly_id}/evidence?dataset_id={self.dataset_id}"
        evidence = client.get(evidence_url, headers={"Authorization": "Bearer synthetic-test-token"})
        self.assertEqual(evidence.status_code, 200)
        self.assertEqual(
            evidence.json["raw_event"]["raw_sha256"],
            hashlib.sha256(LINE.replace(b"INFO", b"ERROR")).hexdigest(),
        )
        self.assertEqual(evidence.json["raw_event"]["source_line"], 2)
        self.assertEqual(evidence.json["detector"]["evidence"]["threshold"], 1)
        self.assertTrue(evidence.json["synthetic"])
        self.assertEqual(client.get(evidence_url).status_code, 403)
        self.assertEqual(
            client.get(
                evidence_url.replace(f"dataset_id={self.dataset_id}", f"dataset_id={self.other_id}"),
                headers={"Authorization": "Bearer synthetic-test-token"},
            ).status_code,
            403,
        )
        self.assertEqual(
            client.get(
                url.replace(f"dataset_id={self.dataset_id}", f"dataset_id={self.other_id}"),
                headers={"Authorization": "Bearer synthetic-test-token"},
            ).status_code,
            403,
        )
        self.app.config.update(DATABASE_READ_TOKEN=None, DATABASE_ALLOWED_DATASETS=())

    def test_20_isolation_forest_persistence(self):
        training = b"".join(LINE.replace(b"example", b"word " * n) for n in range(1, 21))
        path = self.zipped(
            training + LINE.replace(b"INFO", b"ERROR").replace(b"example", b"long rare message " * 50) * 4
        )
        ingest_bgl(self.engine, self.dataset_id, path)
        with tempfile.TemporaryDirectory() as directory:
            result = detect(
                self.engine,
                self.dataset_id,
                kind="isolation_forest",
                train_size=16,
                artifact_root=directory,
            )
            self.assertEqual(result["evaluated_units"], 8)
            self.assertEqual(result["state"], "completed")
            self.assertGreater(result["anomaly_outputs"], 0)
            self.assertEqual(len(list(Path(directory).glob("*.joblib"))), 1)
        with self.session.begin():
            run = self.session.get(DetectorRun, result["run_id"])
            version = self.session.get(DetectorVersion, run.version_id)
            self.assertEqual(version.score_direction, "lower")
            self.assertNotIn("label", version.feature_schema["names"])

    def test_21_second_clean_migration_rebuild(self):
        other_url = os.environ.get("SECOND_TEST_DATABASE_URL")
        if not other_url:
            self.skipTest("Second newly created schema not provided")
        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": other_url})
        assert_isolated(app)
        with app.app_context():
            upgrade()
            self.assertTrue(set(db.metadata.tables) <= set(inspect(db.engine).get_table_names()))
            with db.engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT COUNT(*) FROM log_events")).scalar_one(),
                    0,
                )

    def test_22_cross_dataset_unit_with_valid_run_rejected(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            event = self.event(self.session)
            unit = self.unit(self.session, event)
            run = self.make_run(self.session)
            run.dataset_id = self.other_id
            self.session.flush()
            self.session.add(
                AnomalyOutput(
                    dataset_id=self.other_id,
                    unit_id=unit.id,
                    run_id=run.id,
                    anchor_time=NOW,
                    evidence={},
                )
            )
            self.session.flush()

    def test_23_cross_dataset_run_with_valid_unit_rejected(self):
        with self.assertRaises(IntegrityError), self.session.begin():
            event = self.event(self.session)
            unit = self.unit(self.session, event)
            run = self.make_run(self.session)
            run.dataset_id = self.other_id
            self.session.flush()
            self.session.add(
                AnomalyOutput(
                    dataset_id=self.dataset_id,
                    unit_id=unit.id,
                    run_id=run.id,
                    anchor_time=NOW,
                    evidence={},
                )
            )
            self.session.flush()

    def test_24_import_lease_rejects_second_worker(self):
        from app.services.bgl_ingestion import import_lease

        path = self.zipped(LINE)
        with import_lease(self.engine, self.dataset_id):
            with self.assertRaisesRegex(RuntimeError, "already owns"):
                ingest_bgl(self.engine, self.dataset_id, path)

    def test_25_abandoned_job_recovered_after_lease_release(self):
        with self.session.begin():
            job = ProcessingJob(dataset_id=self.dataset_id, kind="ingestion", state="running")
            self.session.add(job)
            self.session.flush()
            job_id = job.id
        ingest_bgl(self.engine, self.dataset_id, self.zipped(LINE))
        with self.session.begin():
            self.session.expire_all()
            job = self.session.get(ProcessingJob, job_id)
            self.assertEqual((job.state, job.error_code), ("failed", "worker_interrupted"))

    def test_26_byte_budget_keeps_every_line(self):
        long_line = LINE.replace(b"example", b"x" * 131000)
        path = self.zipped(long_line * 70)
        result = ingest_bgl(self.engine, self.dataset_id, path, batch_size=500)
        self.assertEqual((result["physical_lines"], result["parsed_events"]), (70, 70))
        self.assertEqual(result["checkpoint_byte"], len(long_line) * 70)
        with self.session.begin():
            self.assertGreaterEqual(self.session.get(Dataset, self.dataset_id).input_revision, 2)

    def test_27_private_api_validation_and_unicode_auth(self):
        self.app.config.update(
            DATABASE_READ_TOKEN="synthetic-validation-token",
            DATABASE_ALLOWED_DATASETS=(self.dataset_id,),
        )
        self.addCleanup(
            lambda: self.app.config.update(DATABASE_READ_TOKEN=None, DATABASE_ALLOWED_DATASETS=())
        )
        client = self.app.test_client()
        url = f"/api/v1/database/anomalies?dataset_id={self.dataset_id}&run_id=1"
        self.assertEqual(client.get(url, headers={"Authorization": "Bearer é"}).status_code, 403)
        headers = {"Authorization": "Bearer synthetic-validation-token"}
        self.assertEqual(client.get(url + "&limit=0", headers=headers).status_code, 400)
        self.assertEqual(
            client.get(url + "&after_id=" + str(2**70), headers=headers).status_code,
            400,
        )
        self.assertEqual(
            client.get(
                url.replace(f"dataset_id={self.dataset_id}", "dataset_id=" + str(2**70)),
                headers=headers,
            ).status_code,
            400,
        )

    def test_28_missing_raw_evidence_explicit(self):
        with self.session.begin():
            unit = DetectionUnit(
                dataset_id=self.dataset_id,
                unit_key="session-evidence",
                kind="session",
                start_time=NOW,
            )
            self.session.add(unit)
            self.session.flush()
            run = self.make_run(self.session)
            anomaly = AnomalyOutput(
                dataset_id=self.dataset_id,
                run_id=run.id,
                unit_id=unit.id,
                anchor_time=NOW,
                evidence={},
            )
            self.session.add(anomaly)
            self.session.flush()
            from app.services.database_evidence import load_evidence

            result = load_evidence(self.session, self.dataset_id, anomaly.id)
            self.assertIsNone(result["raw_event"])
            self.assertEqual(result["availability"]["raw"], "unavailable")

    def test_29_timezone_and_microsecond_roundtrip(self):
        with self.session.begin():
            local = datetime(2026, 11, 4, 7, 0, 0, 123456, tzinfo=timezone(timedelta(hours=7)))
            event = self.event(self.session, timestamp=local)
            self.session.expire(event)
            self.assertEqual(event.timestamp, NOW + timedelta(microseconds=123456))
            self.assertEqual(event.timestamp.tzinfo, timezone.utc)

    def test_30_empty_source_is_not_fake_coverage(self):
        result = ingest_bgl(self.engine, self.dataset_id, self.zipped(b""))
        self.assertEqual((result["physical_lines"], result["parsed_events"]), (0, 0))
        with self.session.begin():
            self.assertEqual(
                self.session.scalar(
                    select(func.count())
                    .select_from(CoverageInterval)
                    .where(CoverageInterval.dataset_id == self.dataset_id)
                ),
                0,
            )
