"""Frozen artifact guard tests and explicitly guarded real-MySQL integration."""

from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import test_mysql_integration as baseline
import test_platform_mysql as platform

from app.domain import DetectionPrediction, EvaluationReport
from app.models import AnomalyOutput, Dataset, DetectorRun, GroundTruthLabel
from app.services.window_deployment import digest, inspect_study
from app.services.window_detection import FEATURE_NAMES, aggregate_windows, run_windows, second


def make_study(root, dataset_id, maximum=1, revision=0, records=()):
    study_id = uuid4().hex
    directory = Path(root) / study_id
    directory.mkdir()
    with (directory / "test.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")
    model = IsolationForest(n_estimators=4, max_samples=16, random_state=42, n_jobs=1)
    model.fit(np.arange(80, dtype=float).reshape(16, 5))
    joblib.dump({"model": model, "reference": None, "features": "base"}, directory / "selected.joblib")
    start = second(baseline.NOW)
    manifest = {
        "dataset_id": dataset_id,
        "input_revision": revision,
        "maximum_event_id": maximum,
        "seconds": 300,
        "splits": {
            "train_start": start - 1200,
            "train_end": start - 600,
            "validation_end": start,
            "test_end": start + 600,
        },
        "cache": {
            "test": {
                "key": "test.jsonl",
                "sha256": digest(directory / "test.jsonl"),
                "count": len(records) or 1,
            }
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    selection = {
        "manifest_sha256": digest(directory / "manifest.json"),
        "model_artifact": {"key": "selected.joblib", "sha256": digest(directory / "selected.joblib")},
        "threshold": 0.0,
        "comparison": "<",
        "score_direction": "lower",
        "selected": {
            "id": "synthetic-test",
            "features": "base",
            "n_estimators": 4,
            "max_samples": 16,
            "seed": 42,
        },
        "feature_names": FEATURE_NAMES,
    }
    (directory / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
    return study_id, directory


class FrozenStudyGuards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root_patch = patch("app.services.window_deployment.STUDY_ROOT", Path(self.directory.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.study_id, self.path = make_study(self.directory.name, 7)

    def test_valid_contract_inspection_does_not_unpickle(self):
        with patch("app.services.window_deployment.joblib.load") as load:
            manifest, _, _ = inspect_study(self.study_id, 7)
        self.assertEqual(manifest["dataset_id"], 7)
        load.assert_not_called()

    def test_dataset_isolation_before_pickle_loading(self):
        with self.assertRaisesRegex(ValueError, "different dataset"):
            inspect_study(self.study_id, 8)

    def test_missing_selection_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            inspect_study(uuid4().hex, 7)

    def test_path_and_arbitrary_artifact_rejected(self):
        with self.assertRaises(ValueError):
            inspect_study("../" + self.study_id, 7)
        selection_path = self.path / "selection.json"
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        selection["model_artifact"]["key"] = "../../untrusted.joblib"
        selection_path.write_text(json.dumps(selection), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum"):
            inspect_study(self.study_id, 7)

    def test_cache_or_manifest_changes_rejected(self):
        with (self.path / "test.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("{}\n")
        with self.assertRaisesRegex(ValueError, "checksum"):
            inspect_study(self.study_id, 7)
        (self.path / "manifest.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            inspect_study(self.study_id, 7)

    def test_direction_and_nonfinite_threshold_rejected(self):
        selection_path = self.path / "selection.json"
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        selection["score_direction"] = "higher"
        selection_path.write_text(json.dumps(selection), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "scoring"):
            inspect_study(self.study_id, 7)
        selection["score_direction"] = "lower"
        selection["threshold"] = float("nan")
        selection_path.write_text(json.dumps(selection), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "scoring"):
            inspect_study(self.study_id, 7)

    def test_opt_in_template_histogram_preserves_default(self):
        event = SimpleNamespace(
            id=1, timestamp=baseline.NOW, host="host", severity="INFO", message="message 42"
        )
        legacy = list(aggregate_windows([event]))
        contextual = list(aggregate_windows([event], include_templates=True))
        self.assertNotIn("templates", legacy[0])
        self.assertEqual(sum(contextual[0]["templates"].values()), 1)
        self.assertEqual({k: v for k, v in contextual[0].items() if k != "templates"}, legacy[0])


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1", "MySQL frozen-study integration NOT RUN"
)
class FrozenStudyMySQL(unittest.TestCase):
    setUpClass = classmethod(baseline.MySQLIntegrationTests.setUpClass.__func__)
    tearDown = baseline.MySQLIntegrationTests.tearDown
    event = baseline.MySQLIntegrationTests.event
    login = platform.PlatformMySQLTests.login
    headers = platform.PlatformMySQLTests.headers

    def setUp(self):
        baseline.MySQLIntegrationTests.setUp(self)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root_patch = patch("app.services.window_deployment.STUDY_ROOT", Path(self.directory.name))
        root_patch.start()
        self.addCleanup(root_patch.stop)
        with self.session.begin():
            dataset = self.session.get(Dataset, self.dataset_id)
            dataset.state = "partial"
            events = []
            for index in range(2):
                event = self.event(self.session, timestamp=baseline.NOW + timedelta(minutes=index))
                event.host = "host-" + str(index)
                event.severity = "INFO"
                self.session.add(
                    GroundTruthLabel(
                        dataset_id=self.dataset_id,
                        event_id=event.id,
                        source="loghub-bgl",
                        version="original",
                        label="-" if index == 0 else "TEST",
                    )
                )
                events.append(event)
            records = list(aggregate_windows(events, include_templates=True))
            maximum = max(event.id for event in events)
        self.study_id, self.path = make_study(
            self.directory.name, self.dataset_id, maximum=maximum, records=records
        )
        self.configuration = {"detector": "isolation_forest", "study_id": self.study_id}
        self.app.config["SECRET_KEY"] = "synthetic-frozen-study-test-session"
        self.client = self.app.test_client()

    def test_persisted_native_scores_evidence_and_idempotency(self):
        result = run_windows(self.engine, self.dataset_id, "frozen-study", self.configuration)
        with Session(self.engine) as session:
            predictions = session.scalars(
                select(DetectionPrediction).where(DetectionPrediction.run_id == result["run_id"])
            ).all()
            outputs = session.scalars(
                select(AnomalyOutput).where(AnomalyOutput.run_id == result["run_id"])
            ).all()
            report = session.scalar(
                select(EvaluationReport).where(EvaluationReport.run_id == result["run_id"])
            )
            self.assertEqual(len(predictions), 2)
            self.assertEqual(len(outputs), 2)
            self.assertTrue(all(p.score < 0 and p.predicted for p in predictions))
            self.assertEqual(outputs[0].evidence["feature_names"], FEATURE_NAMES)
            self.assertEqual(outputs[0].evidence["explanation"], "Explanation unavailable")
            self.assertEqual(report.metrics["eligible_units"], 2)
            self.assertEqual(report.metrics["tp"], 1)
            self.assertEqual(report.metrics["fp"], 1)
        with patch("app.services.window_deployment.joblib.load") as load:
            again = run_windows(self.engine, self.dataset_id, "frozen-study", self.configuration)
        self.assertEqual(again["run_id"], result["run_id"])
        self.assertEqual(again["retry"], "idempotent")
        load.assert_not_called()

    def test_failed_after_committed_batch_resumes_without_duplicates(self):
        from app.services.window_detection import persist_predictions

        def interrupted(*args, **kwargs):
            persist_predictions(*args, **kwargs)
            raise RuntimeError("Synthetic interruption after committed batch")

        with patch("app.services.window_detection.persist_predictions", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                run_windows(self.engine, self.dataset_id, "resume-study", self.configuration)
        with Session(self.engine) as session:
            run = session.scalar(
                select(DetectorRun).where(
                    DetectorRun.dataset_id == self.dataset_id, DetectorRun.run_key == "resume-study"
                )
            )
            self.assertEqual(run.state, "failed")
            self.assertEqual(run.evaluated_units, 2)
        result = run_windows(self.engine, self.dataset_id, "resume-study", self.configuration)
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(DetectionPrediction)
                    .where(DetectionPrediction.run_id == result["run_id"])
                ),
                2,
            )
            self.assertEqual(session.get(DetectorRun, result["run_id"]).evaluated_units, 2)

    def test_dataset_snapshot_revision_and_cross_dataset_rejected(self):
        with self.assertRaisesRegex(ValueError, "different dataset"):
            run_windows(self.engine, self.other_id, "cross-dataset", self.configuration)
        with Session(self.engine) as session, session.begin():
            session.get(Dataset, self.dataset_id).input_revision += 1
        with self.assertRaisesRegex(ValueError, "snapshot"):
            run_windows(self.engine, self.dataset_id, "changed-input", self.configuration)

    def test_job_api_rejects_scope_override_and_accepts_frozen_job(self):
        self.login("analyst")
        body = {
            "dataset_id": self.dataset_id,
            "idempotency_key": "frozen-api",
            "configuration": self.configuration,
        }
        result = self.client.post("/api/v1/detection/jobs", json=body, headers=self.headers())
        self.assertEqual(result.status_code, 202, result.json)
        for override in (
            {"seed": 3},
            {"window_seconds": 60},
            {"study_id": "../invalid"},
            {"detector": "rule"},
        ):
            body["configuration"] = dict(self.configuration, **override)
            result = self.client.post("/api/v1/detection/jobs", json=body, headers=self.headers())
            self.assertEqual(result.status_code, 400, result.json)
