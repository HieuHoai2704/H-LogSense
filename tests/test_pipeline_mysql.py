"""Pipeline & jobs on real MySQL: job grid and flow from processing_jobs, access, and retry of a failed job."""

import os
import unittest

from sqlalchemy.orm import Session
import test_platform_mysql as platform

from app.models import ProcessingJob

RULE = {"detector": "rule", "window_seconds": 300, "seed": 42}
FOREST = {"detector": "isolation_forest", "window_seconds": 300, "seed": 42}


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Pipeline MySQL integration NOT RUN",
)
class PipelineMySQLTests(unittest.TestCase):
    setUpClass = classmethod(platform.PlatformMySQLTests.setUpClass.__func__)
    setUp = platform.PlatformMySQLTests.setUp
    tearDown = platform.PlatformMySQLTests.tearDown
    login = platform.PlatformMySQLTests.login
    headers = platform.PlatformMySQLTests.headers
    event = platform.PlatformMySQLTests.event

    def seed(self):
        with Session(self.engine) as session, session.begin():
            self.event(session)
            jobs = [
                ProcessingJob(
                    dataset_id=self.dataset_id, kind="ingestion", state="completed", processed_count=1
                ),
                ProcessingJob(
                    dataset_id=self.dataset_id,
                    kind="analysis",
                    state="completed",
                    job_key="pipeline-rule",
                    configuration=RULE,
                    result={"run_id": 7, "alerts": {"created": 2, "suppressed": 0}},
                ),
                ProcessingJob(
                    dataset_id=self.dataset_id,
                    kind="analysis",
                    state="failed",
                    error_code="analysis_failed",
                    job_key="pipeline-forest",
                    configuration=FOREST,
                ),
                # Another dataset's job never shows up here.
                ProcessingJob(dataset_id=self.other_id, kind="analysis", state="failed", configuration=RULE),
            ]
            session.add_all(jobs)
            session.flush()
            return [item.id for item in jobs]

    def fail_job(self, job_id):
        with Session(self.engine) as session, session.begin():
            job = session.get(ProcessingJob, job_id)
            job.state, job.error_code = "failed", "analysis_failed"

    def test_grid_flow_and_retry_of_a_failed_job(self):
        from test_analysis_menu import menu

        ingest, rule, forest, foreign = self.seed()
        self.login("staff")
        report = self.client.get(f"/api/v1/pipeline?dataset_id={self.dataset_id}")
        self.assertEqual(report.status_code, 200, report.json)
        rows = {row["type"]: row for row in report.json["grid"]}
        self.assertEqual(list(rows), ["ingestion", "rule", "isolation_forest"])
        self.assertEqual([run["id"] for run in rows["rule"]["runs"]], [rule])
        self.assertEqual(rows["rule"]["runs"][0]["alerts_created"], 2)
        self.assertEqual(rows["isolation_forest"]["runs"][0]["actions"], ["retry"])
        self.assertNotIn(foreign, [job["id"] for job in report.json["recent"]])
        stages = {stage["key"]: stage["state"] for stage in report.json["flow"]}
        # The fixture event has no host, component or level: quality scores (100 + 0 + 100) / 3 = 67.
        self.assertEqual(
            stages, {"raw": "idle", "import": "ok", "quality": "failed", "ml": "failed", "alerts": "ok"}
        )
        self.assertEqual(self.client.get(f"/api/v1/pipeline?dataset_id={self.other_id}").status_code, 403)

        page = self.client.get(f"/analysis/pipeline?dataset_id={self.dataset_id}&job={forest}")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('data-stage="ml" data-state="failed"', html)
        self.assertIn(f'data-job="{forest}"', html)
        self.assertIn('data-action="retry"', html)
        self.assertEqual(menu(page.data).current, ["pipeline"])
        # A completed job offers a rerun that carries its configuration as JSON.
        html = self.client.get(f"/analysis/pipeline?dataset_id={self.dataset_id}&job={rule}").get_data(
            as_text=True
        )
        self.assertIn('data-action="rerun" data-configuration="{&#34;detector&#34;: &#34;rule&#34;', html)
        # A job of another dataset is not shown even when asked for.
        html = self.client.get(f"/analysis/pipeline?dataset_id={self.dataset_id}&job={foreign}").get_data(
            as_text=True
        )
        self.assertIn("Job not found", html)

        # The page's retry action goes through the existing job API. The schema is shared with other
        # suites whose worker takes the oldest queued job, so never leave this one queued.
        self.addCleanup(self.fail_job, forest)
        retried = self.client.post(f"/api/v1/detection/jobs/{forest}/retry", headers=self.headers())
        self.assertEqual(retried.status_code, 202, retried.json)
        report = self.client.get(f"/api/v1/pipeline?dataset_id={self.dataset_id}").json
        self.assertEqual(report["queued"], 1)
        stages = {stage["key"]: stage["state"] for stage in report["flow"]}
        self.assertEqual(stages["ml"], "running")


if __name__ == "__main__":
    unittest.main()
