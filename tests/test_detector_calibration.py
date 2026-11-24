import unittest

import numpy as np
from sklearn.metrics import average_precision_score

from app.services.detector_calibration import (
    binary_metrics,
    choose_threshold,
    reservoir_sample,
    temporal_split,
)


class DetectorCalibrationTests(unittest.TestCase):
    def test_temporal_split_uses_whole_disjoint_bins(self):
        self.assertEqual(
            temporal_split(0, 3000, 300),
            {"train_start": 0, "train_end": 1500, "validation_end": 2100, "test_end": 3000},
        )
        self.assertEqual(temporal_split(-3000, 0, 300)["train_end"], -1500)
        for args in (
            (0, 0, 300),
            (0, 600, 300),
            (1, 3000, 300),
            (0, 3001, 300),
            (0, 3000, 0),
            (False, 3000, 300),
            (0.0, 3000, 300),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                temporal_split(*args)

    def test_reservoir_is_bounded_deterministic_and_samples_tail(self):
        first = reservoir_sample(iter(range(100000)), limit=100, seed=42)
        self.assertEqual(first, reservoir_sample(iter(range(100000)), 100, 42))
        self.assertEqual(len(first), 100)
        self.assertEqual(len(set(first)), 100)
        self.assertGreater(max(first), 90000)
        self.assertNotEqual(first, reservoir_sample(range(100000), 100, 43))
        self.assertEqual(reservoir_sample(range(3), 100), [0, 1, 2])
        self.assertEqual(reservoir_sample([], 100), [])
        for limit in (0, -1, 2.0, True):
            with self.assertRaises(ValueError):
                reservoir_sample([], limit)

    def test_native_direction_and_strict_boundary(self):
        truth = [1, 0, 0]
        lower = binary_metrics(truth, [-0.8, -0.5, -0.2], -0.5)
        higher = binary_metrics(truth, [0.8, 0.5, 0.2], 0.5, "higher")
        self.assertEqual(lower, higher)
        self.assertEqual((lower["tp"], lower["fp"], lower["tn"]), (1, 0, 2))
        self.assertEqual(binary_metrics(truth, [-0.8, -0.5, -0.2], -0.5, comparison="<=")["fp"], 1)
        self.assertEqual(lower["auprc_average_precision"], 1)

    def test_undefined_metrics_are_null(self):
        empty = binary_metrics([], [], 0)
        for key in ("precision", "recall", "f1", "fpr", "auprc_average_precision"):
            self.assertIsNone(empty[key])
        normal = binary_metrics([0, 0], [0, 1], -1)
        self.assertIsNone(normal["recall"])
        self.assertIsNone(normal["precision"])
        self.assertIsNone(normal["f1"])
        self.assertEqual(normal["fpr"], 0)
        self.assertIsNone(normal["auprc_average_precision"])
        missed = binary_metrics([1], [0], -1)
        self.assertEqual(missed["f1"], 0)
        self.assertIsNone(missed["fpr"])

    def test_validation_ties_are_indivisible(self):
        result = choose_threshold([1, 0, 1, 0], [-1, -1, -0.5, 0], max_fpr=0)
        self.assertEqual(result["metrics"]["predicted_positive"], 0)
        self.assertLess(result["threshold"], -1)
        result = choose_threshold([1, 0, 1, 0], [-1, -1, -0.5, 0], max_fpr=0.5)
        self.assertEqual((result["metrics"]["tp"], result["metrics"]["fp"]), (2, 1))
        self.assertEqual(result["comparison"], "<")

    def test_validation_fpr_constraint_and_higher_direction(self):
        truth = [1, 0, 1, 0, 0, 0]
        scores = [-0.9, -0.8, -0.7, -0.6, -0.5, -0.4]
        constrained = choose_threshold(truth, scores, max_fpr=0.2)
        unconstrained = choose_threshold(truth, scores, max_fpr=1)
        self.assertLessEqual(constrained["metrics"]["fpr"], 0.2)
        self.assertEqual(constrained["metrics"]["tp"], 1)
        self.assertEqual(unconstrained["metrics"]["tp"], 2)
        mirrored = choose_threshold(truth, -np.asarray(scores), 0.2, "higher")
        self.assertEqual(constrained["metrics"], mirrored["metrics"])
        self.assertAlmostEqual(constrained["threshold"], -mirrored["threshold"])

    def test_tie_break_prefers_lower_fpr(self):
        # F1=2/3 both after first alert and after all four; retain first alert.
        result = choose_threshold([1, 0, 0, 1], [-4, -3, -2, -1], max_fpr=1)
        self.assertEqual(result["metrics"]["predicted_positive"], 1)
        self.assertEqual(result["metrics"]["fpr"], 0)

    def test_average_precision_uses_anomaly_direction(self):
        truth = [1, 0, 1, 0]
        scores = [-0.8, -0.7, -0.6, -0.5]
        measured = binary_metrics(truth, scores, -0.75)
        self.assertAlmostEqual(
            measured["auprc_average_precision"], average_precision_score(truth, -np.asarray(scores))
        )

    def test_invalid_inputs_rejected(self):
        for truth, scores in (([1], []), ([[1]], [0]), ([2], [0]), ([0], [np.nan]), ([1], [np.inf])):
            with self.subTest(truth=truth, scores=scores), self.assertRaises(ValueError):
                binary_metrics(truth, scores, 0)
        with self.assertRaises(ValueError):
            binary_metrics([0], [0], np.inf)
        with self.assertRaises(ValueError):
            binary_metrics([0], [0], 0, "probability")
        with self.assertRaises(ValueError):
            binary_metrics([0], [0], 0, comparison=">")
        for labels in ([], [0, 0], [1, 1]):
            with self.assertRaises(ValueError):
                choose_threshold(labels, [0] * len(labels))
        for fpr in (-0.1, 1.1, np.nan):
            with self.assertRaises(ValueError):
                choose_threshold([0, 1], [0, -1], max_fpr=fpr)

    def test_sweep_matches_exhaustive_search(self):
        random = np.random.default_rng(123)
        for direction in ("lower", "higher"):
            truth = random.integers(0, 2, 120)
            scores = random.integers(-5, 5, 120).astype(float)
            result = choose_threshold(truth, scores, 0.4, direction)
            best = (0, 0, 0)
            for value in np.unique(scores):
                threshold = np.nextafter(value, np.inf if direction == "lower" else -np.inf)
                metrics = binary_metrics(truth, scores, threshold, direction)
                if metrics["fpr"] <= 0.4:
                    best = max(best, (metrics["f1"], -metrics["fpr"], -metrics["predicted_positive"]))
            actual = result["metrics"]
            self.assertEqual((actual["f1"], -actual["fpr"], -actual["predicted_positive"]), best)


if __name__ == "__main__":
    unittest.main()
