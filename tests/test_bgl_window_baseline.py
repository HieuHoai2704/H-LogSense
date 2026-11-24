import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from scripts.bgl_window_baseline import calibrate, collect, epoch, fit_representation, transform


class BGLWindowBaselineTest(unittest.TestCase):
    def test_threshold_respects_ties_and_prefers_lower_fpr_at_equal_recall(self):
        y = np.zeros(502, dtype=np.uint8)
        y[:2] = 1
        scores = np.zeros_like(y, dtype=np.float64)
        scores[:3] = (3, 2, 2)
        scores[3] = 1
        threshold, metrics = calibrate(y, scores)
        self.assertLess(threshold, 2)
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (2, 1, 0))
        self.assertEqual(metrics["fpr"], 0.002)

        scores[3] = 2
        _, metrics = calibrate(y, scores)
        self.assertEqual((metrics["tp"], metrics["fp"], metrics["fn"]), (1, 0, 1))

    def test_collect_respects_date_and_host_bounds_and_keeps_label_out_of_text(self):
        date = "2005-08-01"
        start = epoch(date)
        def row(label, time, host, message):
            return f"{label} {time} 2005.08.01 {host} 2005-08-01-00.00.00.000000 {host} RAS KERNEL INFO {message}\n"
        lines = [
            row("BEFORE", start - 1, "R00", "before"),
            row("-", start, "R00", "status 42"),
            row("ALERT_SECRET", start + 299, "R00", "status 0xab"),
            row("-", start + 299, "R01", "status 42"),
            row("-", start + 300, "R00", "status 42"),
            row("-", start + 300, "-", "missing host"),
            row("AFTER", epoch("2005-08-02"), "R00", "after"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "test.zip"
            with ZipFile(archive, "w") as package:
                package.writestr("BGL.log", "".join(lines))
            data = collect(archive, (date, "2005-08-02"))
        self.assertEqual(data["y"].tolist(), [1, 0, 0])
        self.assertEqual(data["first_source_line"].tolist(), [2, 4, 5])
        self.assertEqual(data["catalog"], ["status <*>"])
        self.assertEqual(data["counts"].sum(), 4)
        self.assertEqual(data["source"]["dropped"], {"missing_host": 1})

    def test_unknown_template_keeps_train_vocabulary_and_uses_frozen_projection(self):
        from scipy.sparse import csr_matrix

        catalog = [f"component failure mode {index:04d} handshake pending {index % 7}" for index in range(50)]
        counts = csr_matrix(np.eye(len(catalog), dtype=np.int32))
        trained = fit_representation({"catalog": catalog, "counts": counts})
        vocabulary = dict(trained["vectorizer"].vocabulary_)
        held_out = {"catalog": ["unseen zzq signature"], "counts": csr_matrix([[2]]),
                    "base": np.ones((1, 5), dtype=np.float32)}
        result = transform(held_out, trained)
        self.assertEqual(trained["vectorizer"].vocabulary_, vocabulary)
        self.assertNotIn(held_out["catalog"][0], trained["template_df"])
        self.assertAlmostEqual(float(result["count"][0, 5]), np.log1p(len(catalog)), places=5)
        self.assertEqual(result["count"][:, 6:].nnz, 0)
        self.assertTrue(np.isfinite(result["hybrid"].data).all())


if __name__ == "__main__":
    unittest.main()
