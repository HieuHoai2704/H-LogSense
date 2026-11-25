"""Data quality checks, score and hourly grid, computed from plain counters (no database)."""

from datetime import datetime, timedelta, timezone
import unittest

from app import create_app
from app.services.data_quality import QualityStats, evaluate, level_of, ratio_status

START = datetime(2026, 11, 1, tzinfo=timezone.utc)


def hours(*counts, start=START):
    return {start + timedelta(hours=index): count for index, count in enumerate(counts) if count}


def by_key(report):
    return {check["key"]: check for check in report["checks"]}


class DataQualityTests(unittest.TestCase):
    def test_empty_dataset_is_not_judged(self):
        report = evaluate(QualityStats())
        self.assertIsNone(report["score"])
        self.assertEqual({check["status"] for check in report["checks"]}, {"skipped"})
        self.assertEqual(report["grid"], {"days": [], "max": 0, "truncated": False})

    def test_ratio_limits_are_inclusive(self):
        limits = (0.001, 0.01)
        self.assertEqual(ratio_status(1, 1000, limits), "pass")
        self.assertEqual(ratio_status(2, 1000, limits), "warn")
        self.assertEqual(ratio_status(10, 1000, limits), "warn")
        self.assertEqual(ratio_status(11, 1000, limits), "fail")

    def test_clean_continuous_data_scores_100(self):
        stats = QualityStats(lines=1200, raw_rows=1200, events=1200, hourly=hours(*[100] * 12))
        report = evaluate(stats)
        self.assertEqual(report["score"], 100)
        self.assertEqual(report["passed"], 5)
        self.assertEqual(by_key(report)["volume_drop"]["baseline"], 600)

    def test_each_problem_is_reported_with_its_numbers(self):
        stats = QualityStats(
            lines=100,
            malformed=2,
            raw_rows=98,
            duplicate_rows=2,
            events=98,
            missing={"host": 1, "service": 0, "severity": 1},
            missing_any=2,
            # Two empty hours, then a busier last block.
            hourly=hours(10, 10, 10, 10, 10, 0, 0, 8, 8, 8, 8, 8, 8),
        )
        report = evaluate(stats)
        checks = by_key(report)
        self.assertEqual(
            {key: check["status"] for key, check in checks.items()},
            {
                "malformed": "fail",
                "duplicates": "fail",
                "missing_fields": "warn",
                "time_gaps": "warn",
                "volume_drop": "pass",
            },
        )
        self.assertEqual(report["score"], 40)  # (0 + 0 + 50 + 50 + 100) / 5
        self.assertEqual(checks["missing_fields"]["host"], 1)
        self.assertEqual((checks["time_gaps"]["empty_hours"], checks["time_gaps"]["longest_hours"]), (2, 2))
        self.assertEqual((checks["volume_drop"]["recent"], checks["volume_drop"]["baseline"]), (48, 40))

    def test_long_gap_and_volume_drop_fail(self):
        stats = QualityStats(events=1, hourly=hours(50, 50, 50, 50, 50, 50, 50, 50, 50, 0, 0, 0, 0, 5))
        checks = by_key(evaluate(stats))
        self.assertEqual(checks["time_gaps"]["status"], "fail")
        self.assertEqual(checks["time_gaps"]["longest_hours"], 4)
        self.assertEqual(checks["volume_drop"]["status"], "fail")
        self.assertAlmostEqual(
            checks["volume_drop"]["drop"], 1 - 55 / 300
        )  # last 6 h: 50 + 0 + 0 + 0 + 0 + 5

    def test_volume_needs_a_previous_block(self):
        checks = by_key(evaluate(QualityStats(events=1, hourly=hours(*[3] * 11))))
        self.assertEqual(checks["volume_drop"]["status"], "skipped")

    def test_grid_marks_gaps_and_hours_outside_the_data(self):
        start = START + timedelta(hours=22)
        report = evaluate(QualityStats(events=3, hourly=hours(1, 0, 1000, start=start)))
        days = report["grid"]["days"]
        self.assertEqual([day["date"] for day in days], ["2026-11-01", "2026-11-02"])
        levels = [cell["level"] for day in days for cell in day["cells"]]
        self.assertEqual(levels[21:25], [None, 1, 0, 4])
        self.assertEqual(report["grid"]["max"], 1000)
        self.assertEqual(level_of(1, 1000), 1)

    def test_grid_keeps_the_last_14_days(self):
        stats = QualityStats(events=2, hourly={START: 1, START + timedelta(days=20): 1})
        grid = evaluate(stats)["grid"]
        self.assertEqual(len(grid["days"]), 14)
        self.assertTrue(grid["truncated"])
        self.assertEqual(grid["days"][-1]["date"], "2026-11-21")


class DataQualityPageTests(unittest.TestCase):
    def test_page_and_api_need_the_database(self):
        client = create_app({"TESTING": True}).test_client()
        page = client.get("/analysis/quality")
        self.assertEqual(page.status_code, 503)
        self.assertIn(b"Data quality needs the MySQL database.", page.data)
        self.assertEqual(client.get("/api/v1/quality?dataset_id=1").status_code, 503)


if __name__ == "__main__":
    unittest.main()
