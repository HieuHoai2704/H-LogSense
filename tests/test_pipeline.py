"""Pipeline job grid, job actions and data-flow stage states, from plain job records (no database)."""

import unittest

from app import create_app
from app.services.pipeline import GRID_RUNS, JobRecord, actions, flow, job_grid, job_type, state_of


def job(id, kind="analysis", state="completed", config=None, upload_id=None, result=None):
    return JobRecord(id, kind, state, 10, None, config, result, upload_id)


RULE = {"detector": "rule", "window_seconds": 300, "seed": 42}
FOREST = {"detector": "isolation_forest", "window_seconds": 300, "seed": 42}


class PipelineTests(unittest.TestCase):
    def test_job_types_follow_the_detector_profile(self):
        self.assertEqual(job_type("ingestion", None), "ingestion")
        self.assertEqual(job_type("analysis", None), "rule")
        self.assertEqual(job_type("analysis", RULE), "rule")
        self.assertEqual(job_type("analysis", FOREST), "isolation_forest")
        self.assertEqual(job_type("analysis", {"detector": "isolation_forest", "model_id": "m"}), "validated")
        self.assertEqual(job_type("analysis", {"detector": "isolation_forest", "study_id": "s"}), "study")

    def test_actions_match_the_existing_retry_rules(self):
        self.assertEqual(actions(job(1, state="failed")), ["retry"])
        self.assertEqual(actions(job(1, state="running")), ["retry"])
        self.assertEqual(actions(job(1, state="completed", config=RULE)), ["rerun"])
        self.assertEqual(actions(job(1, state="queued")), [])
        self.assertEqual(actions(job(1, "ingestion", "failed", upload_id="a" * 32)), ["retry_upload"])
        self.assertEqual(
            actions(job(1, "ingestion", "failed")), []
        )  # an archive import has no upload to retry
        self.assertEqual(actions(job(1, "ingestion", "completed", upload_id="a" * 32)), [])

    def test_grid_rows_keep_order_and_the_last_runs(self):
        jobs = [job(i, config=RULE, state="failed" if i == 3 else "completed") for i in range(1, 26)]
        jobs += [job(30, "ingestion"), job(31, config=FOREST, state="queued")]
        grid = job_grid(reversed(jobs))
        self.assertEqual([row["type"] for row in grid], ["ingestion", "rule", "isolation_forest"])
        rule = grid[1]
        self.assertEqual(rule["total"], 25)
        self.assertEqual(len(rule["runs"]), GRID_RUNS)
        self.assertEqual([run["id"] for run in rule["runs"]][:2], [6, 7])  # oldest shown first
        self.assertEqual(grid[2]["latest"], "queued")

    def test_empty_rows_that_are_always_shown(self):
        grid = job_grid([])
        self.assertEqual([row["type"] for row in grid], ["ingestion", "rule", "isolation_forest"])
        self.assertEqual({row["latest"] for row in grid}, {None})

    def test_stage_state_priority(self):
        self.assertEqual(state_of(["completed", "failed", "queued"]), "failed")
        self.assertEqual(state_of(["completed", "queued"]), "running")
        self.assertEqual(state_of(["completed", None]), "ok")
        self.assertEqual(state_of([None, None]), "idle")

    def test_flow_stages(self):
        grid = job_grid([job(1, "ingestion"), job(2, config=RULE), job(3, config=FOREST, state="failed")])
        stages = flow(lines=100, events=98, score=75, grid=grid, anomalies=4, alerts=3, open_alerts=2)
        self.assertEqual(
            [(stage["key"], stage["state"]) for stage in stages],
            [("raw", "ok"), ("import", "ok"), ("quality", "warn"), ("ml", "failed"), ("alerts", "warn")],
        )
        self.assertEqual(stages[4]["total"], 3)
        empty = flow(lines=0, events=0, score=None, grid=job_grid([]), anomalies=0, alerts=0, open_alerts=0)
        self.assertEqual({stage["state"] for stage in empty}, {"idle"})
        # Events loaded without a recorded import job still count as imported.
        loaded = flow(lines=0, events=5, score=100, grid=job_grid([]), anomalies=0, alerts=0, open_alerts=0)
        self.assertEqual(loaded[1]["state"], "ok")

    def test_page_and_api_need_the_database(self):
        client = create_app({"TESTING": True}).test_client()
        page = client.get("/analysis/pipeline")
        self.assertEqual(page.status_code, 503)
        self.assertIn(b"Pipeline status needs the MySQL database.", page.data)
        self.assertEqual(client.get("/api/v1/pipeline?dataset_id=1").status_code, 503)


if __name__ == "__main__":
    unittest.main()
