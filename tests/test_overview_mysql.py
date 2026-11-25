"""Overview on real MySQL: headline numbers, attention items and the hourly volume for a granted dataset."""

from datetime import timedelta
import os
import unittest

from sqlalchemy.orm import Session
import test_platform_mysql as platform

from app.models import ProcessingJob

RULE = {"detector": "rule", "window_seconds": 300, "seed": 42}


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Overview MySQL integration NOT RUN",
)
class OverviewMySQLTests(unittest.TestCase):
    setUpClass = classmethod(platform.PlatformMySQLTests.setUpClass.__func__)
    setUp = platform.PlatformMySQLTests.setUp
    tearDown = platform.PlatformMySQLTests.tearDown
    login = platform.PlatformMySQLTests.login
    event = platform.PlatformMySQLTests.event

    def seed(self):
        with Session(self.engine) as session, session.begin():
            for minute, (host, severity) in enumerate(
                [("R01", "INFO"), ("R01", "ERROR"), ("R02", "FATAL"), ("R02", "INFO")]
            ):
                event = self.event(session, timestamp=platform.NOW + timedelta(minutes=minute))
                event.host, event.service, event.severity = host, "KERNEL", severity
            job = ProcessingJob(
                dataset_id=self.dataset_id,
                kind="analysis",
                state="failed",
                error_code="analysis_failed",
                job_key="overview-failed",
                configuration=RULE,
            )
            session.add(job)
            session.flush()
            return job.id

    def test_numbers_attention_and_access(self):
        failed = self.seed()
        self.login("staff")
        response = self.client.get(f"/api/v1/overview?dataset_id={self.dataset_id}")
        self.assertEqual(response.status_code, 200, response.json)
        report = response.json
        self.assertEqual((report["events"], report["hosts"], report["severe"]), (4, 2, 2))
        self.assertEqual(report["first"], platform.NOW.isoformat())
        kinds = [item["kind"] for item in report["attention"]]
        self.assertEqual(kinds[0], "job_failed")
        self.assertEqual(report["attention"][0]["job"], failed)
        # The fixture repeats one raw line, so the duplicate check fails too.
        self.assertIn("quality", kinds)
        self.assertEqual(sum(bar["total"] for bar in report["volume"]), 4)
        self.assertEqual(self.client.get(f"/api/v1/overview?dataset_id={self.other_id}").status_code, 403)

        from test_analysis_menu import menu

        page = self.client.get(f"/analysis/overview?dataset_id={self.dataset_id}")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('data-kind="job_failed"', html)
        self.assertIn(f"job={failed}", html)
        self.assertEqual(menu(page.data).current, ["overview"])


if __name__ == "__main__":
    unittest.main()
