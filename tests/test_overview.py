"""Overview: the "needs attention" list and the hourly volume, from plain reports (no database)."""

from datetime import datetime, timedelta, timezone
import unittest

from app import create_app
from app.services.overview import VOLUME_HOURS, attention_items, volume
from app.services.pipeline import JobRecord, job_grid

RULE = {"detector": "rule", "window_seconds": 300, "seed": 42}


def quality(*statuses):
    keys = ("malformed", "duplicates", "missing_fields", "time_gaps", "volume_drop")
    return {"checks": [{"key": key, "status": status} for key, status in zip(keys, statuses, strict=False)]}


def pipeline(jobs=(), queued=0):
    return {"grid": job_grid(jobs), "queued": queued}


class OverviewTests(unittest.TestCase):
    def test_nothing_needs_attention_on_healthy_data(self):
        items = attention_items(
            quality=quality("pass", "pass", "pass", "pass", "skipped"),
            pipeline=pipeline([JobRecord(1, "analysis", "completed", 1, None, RULE, None, None)]),
            insights={"error_spikes": [], "new_patterns": []},
            open_alerts=0,
            high_anomalies=0,
        )
        self.assertEqual(items, [])

    def test_items_are_ranked_critical_first(self):
        jobs = [
            JobRecord(1, "analysis", "completed", 1, None, RULE, None, None),
            JobRecord(2, "analysis", "failed", 0, "analysis_failed", RULE, None, None),
        ]
        items = attention_items(
            quality=quality("pass", "fail", "warn", "pass", "pass"),
            pipeline=pipeline(jobs, queued=1),
            insights={
                "error_spikes": [
                    {
                        "start": "2005-06-04T07:10:53.05Z",
                        "end": "2005-06-04T07:49:57Z",
                        "count": 50,
                        "baseline": 2.0,
                    }
                ],
                "new_patterns": [{"pattern": "ciod: <*>", "count": 4, "filter_terms": ["ciod:"]}],
            },
            open_alerts=3,
            high_anomalies=5,
        )
        self.assertEqual(
            [(item["kind"], item["level"]) for item in items],
            [
                ("job_failed", "critical"),
                ("quality", "critical"),
                ("quality", "warn"),
                ("alerts", "warn"),
                ("anomalies", "warn"),
                ("spike", "warn"),
                ("new_pattern", "info"),
                ("queued", "info"),
            ],
        )
        self.assertEqual(items[0]["job"], 2)
        self.assertEqual(items[2]["check"], "missing_fields")
        # Log Explorer time fields take at most milliseconds: the spike range is widened to whole seconds.
        spike = items[5]
        self.assertEqual((spike["start"], spike["end"]), ("2005-06-04T07:10:53Z", "2005-06-04T07:49:57Z"))

    def test_a_job_that_failed_before_a_later_success_is_not_reported(self):
        jobs = [
            JobRecord(1, "analysis", "failed", 0, "analysis_failed", RULE, None, None),
            JobRecord(2, "analysis", "completed", 1, None, RULE, None, None),
        ]
        items = attention_items(
            quality=quality(), pipeline=pipeline(jobs), insights=None, open_alerts=0, high_anomalies=0
        )
        self.assertEqual(items, [])

    def test_volume_keeps_the_last_hours_including_empty_ones(self):
        start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        hourly = {start: (10, 1), start + timedelta(hours=3): (5, 0)}
        bars = volume(hourly)
        self.assertEqual([bar["total"] for bar in bars], [10, 0, 0, 5])
        self.assertEqual(bars[0]["severe"], 1)
        long = {start + timedelta(hours=hour): (1, 0) for hour in range(100)}
        bars = volume(long)
        self.assertEqual(len(bars), VOLUME_HOURS)
        self.assertEqual(bars[-1]["hour"], (start + timedelta(hours=99)).isoformat())
        self.assertEqual(volume({}), [])

    def test_page_and_api_need_the_database(self):
        client = create_app({"TESTING": True}).test_client()
        page = client.get("/analysis/overview")
        self.assertEqual(page.status_code, 503)
        self.assertIn(b"The overview needs the MySQL database.", page.data)
        self.assertEqual(client.get("/api/v1/overview?dataset_id=1").status_code, 503)


if __name__ == "__main__":
    unittest.main()
