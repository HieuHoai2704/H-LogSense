"""Frozen IF artifact guards and actual DB inference, not research metric mocks."""

from datetime import timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import test_mysql_integration as baseline

from app.domain import DetectionPrediction, EvaluationReport
from app.models import AnomalyOutput, Dataset, DetectionUnit, DetectorRun, DetectorVersion, UnitEvent
from app.services.bgl_ingestion import fingerprint
import app.services.validated_if as validated
from app.services.window_detection import second


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def fixture(root, cutoff):
    model_id = uuid4().hex
    directory = Path(root) / model_id
    directory.mkdir()
    spec = {"id": "synthetic-fixture", "features": "base", "n_estimators": 4, "max_samples": 16, "seed": 42}
    protocol = {
        "seconds": 300,
        "max_fpr": 0.01,
        "splits": {
            "train_start": second(cutoff) - 1200,
            "train_end": second(cutoff) - 600,
            "validation_end": second(cutoff),
            "test_end": second(cutoff) + 86400,
        },
    }
    save(directory / "protocol.json", protocol)
    manifest = dict(protocol, protocol_sha256=fingerprint(directory / "protocol.json"))
    save(directory / "manifest.json", manifest)
    validation = {
        "selected": spec["id"],
        "eligible_units": 100,
        "candidates": [{"spec": spec, "calibration": {"threshold": 0.0}}],
    }
    save(directory / "validation.json", validation)
    model = IsolationForest(n_estimators=4, max_samples=16, random_state=42, n_jobs=1)
    model.fit(np.arange(80, dtype=float).reshape(16, 5))
    joblib.dump({"model": model, "reference": None, "features": "base"}, directory / "selected.joblib")
    selection = {
        "selected": spec,
        "threshold": 0.0,
        "comparison": "<",
        "score_direction": "lower",
        "threshold_uses_validation_labels": True,
        "manifest_sha256": fingerprint(directory / "manifest.json"),
        "validation_sha256": fingerprint(directory / "validation.json"),
        "selected_artifact_sha256": fingerprint(directory / "selected.joblib"),
    }
    save(directory / "selection.json", selection)
    return model_id, directory


class ValidatedIFArtifactGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cutoff = baseline.NOW - timedelta(days=2)
        self.model_id, self.path = fixture(self.temp.name, self.cutoff)
        patcher = patch.object(validated, "STUDY_ROOT", Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_model_card_checks_metadata_without_loading_pickle(self):
        with patch.object(validated.joblib, "load") as load:
            card = validated.model_card(self.model_id)
        load.assert_not_called()
        self.assertEqual(card["inference_start_utc"], self.cutoff.isoformat())
        self.assertFalse(card["score_is_probability"])
        self.assertTrue(card["calibration"]["uses_validation_labels"])
        self.assertNotIn("path", json.dumps(card).lower())

    def test_traversal_and_missing_model_fail_closed(self):
        for model_id in ("../" + self.model_id, "bad", uuid4().hex):
            with self.subTest(model=model_id), self.assertRaises(ValueError):
                validated.load_frozen_model(model_id)

    def test_modified_artifact_is_rejected_before_pickle_loading(self):
        with (self.path / "selected.joblib").open("ab") as stream:
            stream.write(b"changed")
        with patch.object(validated.joblib, "load") as load:
            with self.assertRaisesRegex(ValueError, "integrity"):
                validated.load_frozen_model(self.model_id)
            load.assert_not_called()

    def test_modified_threshold_cannot_bypass_frozen_validation_choice(self):
        selection = json.loads((self.path / "selection.json").read_text())
        selection["threshold"] = -0.75
        save(self.path / "selection.json", selection)
        with self.assertRaisesRegex(ValueError, "contract"):
            validated.model_card(self.model_id)

    def test_load_validated_feature_schema_and_native_score(self):
        bundle, card = validated.load_frozen_model(self.model_id)
        score = bundle["model"].score_samples(np.zeros((1, 5)))[0]
        self.assertTrue(np.isfinite(score))
        self.assertEqual(card["score_direction"], "lower")
        self.assertEqual(card["comparison"], "<")
        self.assertEqual(len(card["feature_names"]), 5)


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Validated IF MySQL tests NOT RUN (explicit opt-in required)",
)
class ValidatedIFMySQLTests(unittest.TestCase):
    setUpClass = classmethod(baseline.MySQLIntegrationTests.setUpClass.__func__)
    tearDown = baseline.MySQLIntegrationTests.tearDown
    event = baseline.MySQLIntegrationTests.event

    def setUp(self):
        baseline.MySQLIntegrationTests.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cutoff = baseline.NOW - timedelta(days=2)
        self.model_id, self.path = fixture(self.temp.name, self.cutoff)
        for name, value in (
            ("STUDY_ROOT", Path(self.temp.name)),
            ("INPUT_ROOT", Path(self.temp.name) / "actual-db-inputs"),
        ):
            patcher = patch.object(validated, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.config = {"detector": "isolation_forest", "model_id": self.model_id}

    def seed(self, stamps, *, host="actual-db-host", dataset=None):
        dataset_id = dataset or self.dataset_id
        event_ids = []
        with Session(self.engine) as session, session.begin():
            original = self.dataset_id
            self.dataset_id = dataset_id
            try:
                for stamp in stamps:
                    item = self.event(session, timestamp=stamp)
                    item.host, item.severity = host, "ERROR"
                    item.message = "Synthetic test of actual DB inference"
                    event_ids.append(item.id)
            finally:
                self.dataset_id = original
            source = session.get(Dataset, dataset_id)
            source.state, source.input_revision = "partial", 1
        return event_ids

    def test_01_actual_ids_scores_and_evidence_with_no_invented_ground_truth(self):
        old_ids = self.seed([self.cutoff - timedelta(seconds=1)])
        eligible = self.seed(
            [self.cutoff + timedelta(seconds=1), self.cutoff + timedelta(minutes=5, seconds=1)]
        )
        result = validated.run_validated(self.engine, self.dataset_id, "validated-native", self.config)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["eligible_units"], 2)
        self.assertEqual(result["scope_counts"]["excluded_pre_cutoff_events"], 1)
        self.assertEqual(result["scope_counts"]["excluded_pre_cutoff_units"], 1)
        with Session(self.engine) as session:
            run = session.get(DetectorRun, result["run_id"])
            rows = session.scalars(
                select(DetectionPrediction)
                .where(DetectionPrediction.run_id == run.id)
                .order_by(DetectionPrediction.unit_id)
            ).all()
            self.assertEqual(len(rows), 2)
            bundle, card = validated.load_frozen_model(self.model_id)
            scores = bundle["model"].score_samples(np.asarray([r.features["values"] for r in rows]))
            for row, score in zip(rows, scores, strict=True):
                self.assertEqual(row.score, score)
                self.assertEqual(row.predicted, bool(score < card["threshold"]))
            membership = set(
                session.scalars(select(UnitEvent.event_id).where(UnitEvent.dataset_id == self.dataset_id))
            )
            self.assertEqual(membership, set(eligible))
            self.assertTrue(membership.isdisjoint(old_ids))
            outputs = session.scalars(select(AnomalyOutput).where(AnomalyOutput.run_id == run.id)).all()
            self.assertEqual(len(outputs), 2)
            self.assertEqual(outputs[0].evidence["explanation"], "Explanation unavailable")
            version = session.get(DetectorVersion, run.version_id)
            self.assertEqual(version.version, card["version"])
            self.assertEqual(version.score_direction, "lower")
            report = session.scalar(select(EvaluationReport.metrics).where(EvaluationReport.run_id == run.id))
            self.assertEqual(report["eligible_units"], 0)
            self.assertIsNone(report["precision"])
            self.assertIsNone(report["recall"])
        retry = validated.run_validated(self.engine, self.dataset_id, "validated-native", self.config)
        self.assertEqual(retry, {"run_id": result["run_id"], "state": "completed", "retry": "idempotent"})

    def test_02_precalibration_dataset_rejected_without_output(self):
        self.seed([self.cutoff - timedelta(seconds=1)])
        with self.assertRaisesRegex(ValueError, "temporal leakage"):
            validated.run_validated(self.engine, self.dataset_id, "too-early", self.config)
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(
                    select(func.count())
                    .select_from(DetectorRun)
                    .where(DetectorRun.dataset_id == self.dataset_id)
                ),
                0,
            )

    def test_03_dataset_isolation_and_changed_revision_retry_rejected(self):
        main = self.seed([self.cutoff + timedelta(seconds=1)], host="main-host")
        other = self.seed([self.cutoff + timedelta(seconds=1)], host="other-host", dataset=self.other_id)
        result = validated.run_validated(self.engine, self.dataset_id, "isolated", self.config)
        with Session(self.engine) as session, session.begin():
            membership = set(
                session.scalars(select(UnitEvent.event_id).where(UnitEvent.dataset_id == self.dataset_id))
            )
            self.assertEqual(membership, set(main))
            self.assertTrue(membership.isdisjoint(other))
            self.assertEqual(session.get(DetectorRun, result["run_id"]).dataset_id, self.dataset_id)
            session.get(Dataset, self.dataset_id).input_revision = 2
        with self.assertRaisesRegex(ValueError, "Retry input/model changed"):
            validated.run_validated(self.engine, self.dataset_id, "isolated", self.config)

    def test_04_open_future_and_unknown_host_are_excluded(self):
        self.seed([self.cutoff + timedelta(seconds=1)])
        self.seed([datetime_now() + timedelta(hours=2)])
        self.seed([self.cutoff + timedelta(seconds=2)], host=None)
        result = validated.run_validated(self.engine, self.dataset_id, "closed-only", self.config)
        self.assertEqual(result["eligible_units"], 1)
        self.assertEqual(result["scope_counts"]["excluded_open_or_future_events"], 1)
        self.assertEqual(result["scope_counts"]["unknown_host_events_in_eligible_time"], 1)

    def test_05_interrupted_committed_batch_resumes_without_duplicate_units(self):
        self.seed([self.cutoff + timedelta(seconds=1, minutes=5 * i) for i in range(201)])
        original = validated.persist_predictions
        calls = []

        def interrupt(*args, **kwargs):
            original(*args, **kwargs)
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("Synthetic failure after committed inference batch")

        with patch.object(validated, "persist_predictions", interrupt), self.assertRaises(RuntimeError):
            validated.run_validated(self.engine, self.dataset_id, "resume-profile", self.config)
        with Session(self.engine) as session:
            run = session.scalar(select(DetectorRun).where(DetectorRun.dataset_id == self.dataset_id))
            self.assertEqual(run.state, "failed")
            self.assertEqual(run.evaluated_units, 200)
        result = validated.run_validated(self.engine, self.dataset_id, "resume-profile", self.config)
        with Session(self.engine) as session:
            run = session.get(DetectorRun, result["run_id"])
            self.assertEqual((run.state, run.evaluated_units), ("completed", 201))
            for model in (DetectionUnit, DetectionPrediction, AnomalyOutput):
                self.assertEqual(
                    session.scalar(
                        select(func.count()).select_from(model).where(model.dataset_id == self.dataset_id)
                    ),
                    201,
                )

    def test_06_default_scope_includes_window_anchor_before_first_raw_timestamp(self):
        self.seed([self.cutoff + timedelta(seconds=30)])
        validated.run_validated(self.engine, self.dataset_id, "first-window-anchor", self.config)
        token = "synthetic-validated-first-anchor-read"
        self.app.config.update(
            DATABASE_READ_TOKEN=token, DATABASE_ALLOWED_DATASETS=(self.dataset_id, self.other_id)
        )
        self.addCleanup(self.app.config.pop, "DATABASE_READ_TOKEN", None)
        self.addCleanup(self.app.config.pop, "DATABASE_ALLOWED_DATASETS", None)
        client = self.app.test_client()
        headers = {"Authorization": "Bearer " + token}
        query = {"source": "db-" + str(self.dataset_id)}
        default = client.get("/api/v1/investigation", query_string=query, headers=headers)
        self.assertEqual(default.status_code, 200, default.json)
        self.assertEqual(default.json["scope_count"], 1)
        self.assertEqual(default.json["result_count"], 1)
        lower = datetime_from_iso(default.json["state"]["start_time"])
        self.assertLessEqual(lower, self.cutoff)
        explicit = client.get(
            "/api/v1/investigation",
            query_string=dict(
                query,
                start_time=(self.cutoff + timedelta(seconds=30)).isoformat(),
                end_time=(self.cutoff + timedelta(seconds=60)).isoformat(),
            ),
            headers=headers,
        )
        self.assertEqual(explicit.status_code, 200, explicit.json)
        self.assertEqual(explicit.json["scope_count"], 0)
        empty = client.get(
            "/api/v1/investigation", query_string={"source": "db-" + str(self.other_id)}, headers=headers
        )
        self.assertEqual(empty.status_code, 200, empty.json)
        self.assertEqual(empty.json["scope_count"], 0)


def datetime_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def datetime_from_iso(value):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    unittest.main()
