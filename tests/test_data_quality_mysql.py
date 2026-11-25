"""Data quality on real MySQL: counters, duplicate and missing-field queries, hourly buckets and access."""

from datetime import timedelta
import os
import unittest

from sqlalchemy.orm import Session
import test_platform_mysql as platform

from app.models import LogEvent, RawLogRecord, SourceArtifact

HOUR0 = platform.NOW.replace(minute=0, second=0, microsecond=0)
HOURLY = [10, 10, 10, 10, 10, 0, 0, 8, 8, 8, 8, 8, 8]  # 98 events, two empty hours


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Data quality MySQL integration NOT RUN",
)
class DataQualityMySQLTests(unittest.TestCase):
    setUpClass = classmethod(platform.PlatformMySQLTests.setUpClass.__func__)
    setUp = platform.PlatformMySQLTests.setUp
    tearDown = platform.PlatformMySQLTests.tearDown
    login = platform.PlatformMySQLTests.login

    def seed(self):
        """100 lines read, 2 malformed; 98 stored lines of which 2 repeat earlier ones; 2 events lack a field."""
        with Session(self.engine) as session, session.begin():
            artifact = SourceArtifact(
                dataset_id=self.dataset_id,
                artifact_key="quality-fixture",
                sha256="b" * 64,
                byte_length=10_000,
                parser_version="test",
                checkpoint_line=100,
                checkpoint_byte=5_000,
                parsed_count=98,
                malformed_count=2,
            )
            session.add(artifact)
            session.flush()
            index = 0
            for hour, count in enumerate(HOURLY):
                for minute in range(count):
                    line = f"line {index % 96}\n".encode()  # lines 96 and 97 repeat lines 0 and 1
                    raw = RawLogRecord(
                        dataset_id=self.dataset_id,
                        artifact_id=artifact.id,
                        line_number=index + 1,
                        byte_offset=index * 10,
                        raw_bytes=line,
                    )
                    session.add(raw)
                    session.flush()
                    session.add(
                        LogEvent(
                            dataset_id=self.dataset_id,
                            raw_id=raw.id,
                            parser_version="test",
                            timestamp=HOUR0 + timedelta(hours=hour, minutes=minute),
                            raw_timestamp="original",
                            host=None if index == 0 else "R01",
                            service="KERNEL",
                            severity=None if index == 1 else "INFO",
                            message="example",
                            attributes={},
                        )
                    )
                    index += 1

    def test_report_counts_on_mysql_and_respects_grants(self):
        from test_analysis_menu import menu

        self.seed()
        self.login("staff")
        response = self.client.get(f"/api/v1/quality?dataset_id={self.dataset_id}")
        self.assertEqual(response.status_code, 200, response.json)
        report = response.json
        checks = {check["key"]: check for check in report["checks"]}
        self.assertEqual((checks["malformed"]["count"], checks["malformed"]["total"]), (2, 100))
        self.assertEqual((checks["duplicates"]["count"], checks["duplicates"]["total"]), (2, 98))
        self.assertEqual(
            {key: checks["missing_fields"][key] for key in ("count", "host", "service", "severity")},
            {"count": 2, "host": 1, "service": 0, "severity": 1},
        )
        self.assertEqual((checks["time_gaps"]["empty_hours"], checks["time_gaps"]["hours"]), (2, 13))
        self.assertEqual((checks["volume_drop"]["recent"], checks["volume_drop"]["baseline"]), (48, 40))
        self.assertEqual(report["score"], 40)
        self.assertEqual(report["first_hour"], HOUR0.isoformat())
        first_day = report["grid"]["days"][0]["cells"]
        self.assertEqual(first_day[HOUR0.hour]["count"], 10)
        # Another dataset is not granted to this account.
        self.assertEqual(self.client.get(f"/api/v1/quality?dataset_id={self.other_id}").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/quality").status_code, 400)
        page = self.client.get(f"/analysis/quality?dataset_id={self.dataset_id}")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('data-check="malformed" data-status="fail"', html)
        self.assertIn('data-check="time_gaps" data-status="warn"', html)
        self.assertIn('style="--score: 40"', html)
        self.assertEqual(menu(page.data).current, ["quality"])
        self.assertEqual(menu(page.data).links["quality"], f"/analysis/quality?dataset_id={self.dataset_id}")

    def test_account_without_grants_sees_no_dataset(self):
        self.login("staff", grant=False)
        page = self.client.get(f"/analysis/quality?dataset_id={self.dataset_id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"No dataset access has been granted.", page.data)
        self.assertNotIn(b"data-check=", page.data)


if __name__ == "__main__":
    unittest.main()
