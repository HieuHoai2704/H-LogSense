"""Study-stage guards with real small IF fits and no database dependency."""

from contextlib import ExitStack, redirect_stdout
from datetime import timedelta
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from scripts.ml import audit_isolation_forest as study


class IsolationStudyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(study, "ROOT", self.root))
        self.stack.enter_context(patch.object(study, "verify_snapshot"))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.study_id = "a" * 32
        self.engine = object()
        self.truth = np.asarray([0] * 20 + [1] * 20, dtype=np.int8)

    @staticmethod
    def unit(index, start=0, label=None):
        count = 1 + index % 6
        record = {
            "host": "host-" + str(index % 4),
            "bucket": start + index,
            "count": count,
            "sample_ids": [index + 1],
            "features": [math.log1p(count), (index % 5) / 5, 1 / count, 1.0, math.log1p(40 + index % 9)],
            "templates": {"template-" + str(index % 7): count},
        }
        if label is not None:
            record["ground_truth_label"] = label
        return record

    def fixture(self, study_id=None):
        study_id = study_id or self.study_id
        root = self.root / study_id
        root.mkdir()
        protocol = {
            "study_id": study_id,
            "dataset_id": 3,
            "input_revision": 2000,
            "maximum_event_id": 1110000,
            "parsed_event_count": 128,
            "seconds": 300,
            "splits": {"train_start": 0, "train_end": 14400, "validation_end": 26400, "test_end": 38400},
            "split_iso_utc": {"train_start": "1970-01-01T00:00:00+00:00", "train_end": "1970-01-01T04:00:00+00:00", "validation_end": "1970-01-01T07:20:00+00:00", "test_end": "1970-01-01T10:40:00+00:00"},
            "candidate_grid": study.CANDIDATES,
            "reservoir_limit": 20000,
            "reservoir_seed": 42,
            "minimum_validation_each_class": 20,
            "max_fpr": 0.01,
            "threshold_sensitivity_quantiles": [0.001, 0.005, 0.01, 0.02, 0.05],
            "seed_sensitivity": [17, 73],
            "software": {"test": "small real IF fits"},
            "unit": "observed UTC host-window",
            "coverage": "unknown",
        }
        study.write_json(root / "protocol.json", protocol)
        cache = {}
        for phase, length, start in (("train", 48, 0), ("validation", 40, 48), ("test", 40, 88)):
            path = root / (phase + ".jsonl")
            path.write_text("".join(json.dumps(self.unit(i, start, label="NOT_A_FEATURE")) + "\n" for i in range(length)), encoding="utf-8")
            cache[phase] = {"key": path.name, "sha256": study.digest(path), "count": length}
        manifest = dict(protocol, protocol_sha256=study.digest(root / "protocol.json"), cache=cache,
                        phase_event_counts={"train": 168, "validation": 136, "test": 136},
                        singleton_units={"train": 8, "validation": 7, "test": 7})
        study.write_json(root / "manifest.json", manifest)
        return root

    def validate(self, root, guard_test=True):
        requested = []

        def validation_labels(engine, manifest, phase, path):
            requested.append(phase)
            self.assertEqual(phase, "validation", "Validation queried test labels")
            self.assertEqual(path.name, "validation.jsonl")
            return self.truth.copy()

        actual_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if guard_test and path.name == "test.jsonl":
                raise AssertionError("Validation opened future test features")
            return actual_open(path, *args, **kwargs)

        with patch.object(study, "labels", side_effect=validation_labels), patch.object(Path, "open", guarded_open):
            study.validate(self.engine, root.name)
        self.assertEqual(requested, ["validation"])
        return study.read_json(root / "selection.json")

    def test_prepare_registers_protocol_before_features_and_refuses_overwrite(self):
        session = MagicMock()
        session.get.return_value = SimpleNamespace(state="partial", input_revision=7)
        session.execute.side_effect = [SimpleNamespace(one=lambda: (study.EPOCH, study.EPOCH + timedelta(seconds=3599), 3, 3)), []]
        manager = MagicMock()
        manager.__enter__.return_value = session
        root = self.root / self.study_id

        def aggregate(*args, **kwargs):
            self.assertTrue((root / "protocol.json").exists())
            self.assertFalse((root / "manifest.json").exists())
            return [self.unit(0), self.unit(0, 6), self.unit(0, 9)]

        with patch.object(study, "Session", return_value=manager), patch.object(study, "aggregate_windows", side_effect=aggregate), patch.object(study, "labels", side_effect=AssertionError("Prepare must not query labels")):
            study.prepare(self.engine, 3, self.study_id)
            before = (root / "protocol.json").read_bytes()
            with self.assertRaises(FileExistsError):
                study.prepare(self.engine, 3, self.study_id)
            self.assertEqual((root / "protocol.json").read_bytes(), before)
        manifest = study.read_json(root / "manifest.json")
        self.assertEqual(manifest["protocol_sha256"], study.digest(root / "protocol.json"))
        self.assertEqual([manifest["cache"][p]["count"] for p in ("train", "validation", "test")], [1, 1, 1])

    def test_validation_never_opens_test_features_or_queries_test_labels(self):
        root = self.fixture()
        selection = self.validate(root)
        self.assertTrue(selection["threshold_uses_validation_labels"])
        self.assertEqual(selection["score_direction"], "lower")
        self.assertEqual(selection["comparison"], "<")
        self.assertEqual(selection["manifest_sha256"], study.digest(root / "manifest.json"))
        self.assertFalse((root / "test-access.json").exists())
        with self.assertRaisesRegex(ValueError, "already frozen"):
            study.validate(self.engine, root.name)

    def test_test_refuses_missing_selection_and_never_accesses_labels(self):
        root = self.fixture()
        with patch.object(study, "labels", side_effect=AssertionError("Must refuse before labels")), self.assertRaises(FileNotFoundError):
            study.test(self.engine, root.name)
        self.assertFalse((root / "test-access.json").exists())

    def test_test_refuses_changed_manifest_before_labels(self):
        root = self.fixture()
        self.validate(root)
        with (root / "manifest.json").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with patch.object(study, "labels", side_effect=AssertionError("Must refuse before labels")), self.assertRaisesRegex(ValueError, "Frozen configuration changed"):
            study.test(self.engine, root.name)
        self.assertFalse((root / "test-access.json").exists())

    def test_validation_refuses_manifest_that_changes_registered_protocol(self):
        root = self.fixture()
        manifest = study.read_json(root / "manifest.json")
        manifest["max_fpr"] = 1.0
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with patch.object(study, "labels", side_effect=AssertionError("Changed protocol queried labels")), self.assertRaises(ValueError):
            study.validate(self.engine, root.name)
        self.assertFalse((root / "selection.json").exists())

    def test_validation_refuses_insufficient_classes_without_test_fallback(self):
        root = self.fixture()
        with patch.object(study, "labels", return_value=np.zeros(40, dtype=np.int8)) as label_query, self.assertRaisesRegex(ValueError, "Insufficient validation classes"):
            study.validate(self.engine, root.name)
        self.assertEqual(label_query.call_args.args[2], "validation")
        self.assertEqual(label_query.call_count, 1)
        self.assertFalse((root / "selection.json").exists())

    def test_test_refuses_threshold_changed_after_validation(self):
        root = self.fixture()
        self.validate(root)
        selected = study.read_json(root / "selection.json")
        selected["threshold"] = selected["threshold"] + 0.1
        (root / "selection.json").write_text(json.dumps(selected), encoding="utf-8")
        with patch.object(study, "labels", side_effect=AssertionError("Changed threshold accessed test labels")), self.assertRaises(ValueError):
            study.test(self.engine, root.name)
        self.assertFalse((root / "test-access.json").exists())

    def test_test_refuses_changed_artifact_before_unpickling_or_labels(self):
        root = self.fixture()
        self.validate(root)
        with (root / "selected.joblib").open("ab") as stream:
            stream.write(b"altered")
        with patch.object(study.joblib, "load", side_effect=AssertionError("Untrusted model loaded")), patch.object(study, "labels", side_effect=AssertionError("Must refuse before labels")), self.assertRaisesRegex(ValueError, "artifact checksum mismatch"):
            study.test(self.engine, root.name)
        self.assertFalse((root / "test-access.json").exists())

    def test_selection_and_access_marker_exist_before_test_labels_are_requested(self):
        root = self.fixture()
        self.validate(root)
        original_selection = (root / "selection.json").read_bytes()

        def test_labels(engine, manifest, phase, path):
            self.assertEqual(phase, "test")
            self.assertEqual(path.name, "test.jsonl")
            self.assertEqual((root / "selection.json").read_bytes(), original_selection)
            marker = study.read_json(root / "test-access.json")
            self.assertEqual(marker["selection_sha256"], study.digest(root / "selection.json"))
            return self.truth.copy()

        with patch.object(study, "labels", side_effect=test_labels):
            study.test(self.engine, root.name)
        self.assertTrue((root / "test-results.json").exists())
        with patch.object(study, "labels", side_effect=AssertionError("Repeat accessed test labels")), self.assertRaisesRegex(ValueError, "already accessed"):
            study.test(self.engine, root.name)

    def test_future_feature_perturbation_cannot_change_validation_selection(self):
        first = self.fixture()
        second = self.fixture("b" * 32)
        # Intentionally make test data unreadable. Validation must not inspect it,
        # even to verify its digest, and must freeze the same learned model.
        (second / "test.jsonl").write_text("future data deliberately invalid\n", encoding="utf-8")
        selected_a = self.validate(first)
        selected_b = self.validate(second)
        for key in ("selected", "threshold", "comparison", "feature_names", "model_artifact", "baseline_artifact_sha256"):
            self.assertEqual(selected_a[key], selected_b[key], key)

    def test_label_fields_never_enter_unsupervised_fit_matrix(self):
        root = self.fixture()
        captured = []
        original = study.fit_model

        def fit(spec, matrix):
            captured.append(matrix.copy())
            self.assertIn(matrix.shape[1], {5, 9})
            self.assertEqual(matrix.dtype, np.float64)
            self.assertTrue(np.all(np.isfinite(matrix)))
            self.assertEqual(matrix.shape[0], 48)
            return original(spec, matrix)

        with patch.object(study, "fit_model", side_effect=fit):
            self.validate(root)
        self.assertEqual(len(captured), 7)  # legacy, four registered, two seed checks


if __name__ == "__main__":
    unittest.main()
