"""Window evaluation metrics: trusted Loghub labels vs separately reported user-supplied labels."""

import unittest

from app.services.window_detection import SUPPLIED_LABELS, TRUSTED_LABELS, window_metrics


class WindowMetricsTest(unittest.TestCase):
    def test_counts_rates_and_label_provenance(self):
        metrics = window_metrics(
            [1, 0, 1, 0],
            [1, 1, 0, 0],
            [0.9, 0.8, 0.2, 0.1],
            3,
            "uploaded-bgl supplied (user-provided, not verified)",
            "policy",
        )
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]), (1, 1, 1, 1))
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["unlabeled_units"], 3)
        self.assertEqual(metrics["label_source"], "uploaded-bgl supplied (user-provided, not verified)")
        self.assertIsNotNone(metrics["auprc_average_precision"])

    def test_empty_or_one_class_input_has_no_undefined_rates(self):
        metrics = window_metrics([], [], [], 5, "loghub-bgl original", "policy")
        self.assertIsNone(metrics["precision"])
        self.assertIsNone(metrics["auprc_average_precision"])
        self.assertEqual(metrics["eligible_units"], 0)

    def test_label_sources_match_ingestion(self):
        from app.services import uploads

        self.assertEqual(TRUSTED_LABELS, ("loghub-bgl", "original"))
        self.assertEqual(SUPPLIED_LABELS, (uploads.LABEL_SOURCE, uploads.LABEL_VERSION))


if __name__ == "__main__":
    unittest.main()
