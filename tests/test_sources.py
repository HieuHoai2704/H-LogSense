"""Every investigation route reaches the right backend with the same response shapes.

The persisted-dataset backend is replaced by fakes here, so this needs no MySQL server; the SQL itself is
covered by the *_mysql suites.
"""

import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from app.api import sources
from app.services import investigation
from app.services.investigation import QueryError

DB = "source=db-7"


def database_view():
    """A real view built from the fixtures, relabelled as a persisted dataset."""
    with create_app({"TESTING": True}).test_request_context():
        view = investigation.build(investigation.query({"source": "demo"}))
    view["state"]["source"] = "db-7"
    return {**view, "mode": "database", "revision": "mysql-runs-1"}


EVIDENCE = {
    "anomaly": {"id": "DB-5"},
    "raw_event": {"page": {"text": "raw"}},
    "related_events": {"items": []},
}


class DatabaseSourceRoutingTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()
        mysql = sources.mysql_investigation
        self.state = patch.object(mysql, "state", return_value={"source": "db-7"}).start()
        self.view = database_view()
        self.build = patch.object(mysql, "build", side_effect=lambda _: self.view).start()
        self.evidence = patch.object(
            sources.database_evidence, "evidence", side_effect=lambda *_: dict(EVIDENCE)
        ).start()
        self.demo = patch.object(
            sources.investigation, "build", side_effect=AssertionError("demo used")
        ).start()
        self.addCleanup(patch.stopall)

    def get(self, path, **kwargs):
        response = self.client.get(f"{path}?{DB}", **kwargs)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response

    def test_views(self):
        self.assertEqual(self.get("/api/v1/investigation").json["mode"], "database")
        timeline = self.get("/api/v1/anomalies/timeline").json
        self.assertEqual(
            set(timeline),
            {
                "state",
                "revision",
                "mode",
                "scope_count",
                "high_critical_count",
                "timeline",
                "coverage",
                "row_count",
                "row_page_count",
            },
        )
        results = self.get("/api/v1/anomalies").json
        self.assertEqual(results["events"], self.view["events"])
        self.assertTrue(self.state.called)
        self.demo.assert_not_called()

    def test_evidence_routes(self):
        self.assertEqual(
            self.get("/api/v1/anomalies/DB-5").json, {"event": {"id": "DB-5"}, "mode": "database"}
        )
        self.assertEqual(self.get("/api/v1/anomalies/DB-5/evidence").json, EVIDENCE)
        self.assertEqual(
            self.get("/api/v1/anomalies/DB-5/evidence/raw").json,
            {"raw_event": {"text": "raw"}, "mode": "database"},
        )
        self.assertEqual(
            self.get("/api/v1/anomalies/DB-5/related").json,
            {"related_events": {"items": []}, "mode": "database"},
        )
        exported = self.get("/api/v1/anomalies/DB-5/evidence/export").json
        self.assertEqual(
            exported["export_scope"], "Current redacted raw/related page; actual persisted evidence."
        )
        self.evidence.assert_called_with("DB-5", unittest.mock.ANY)

    def test_query_errors_are_400_json(self):
        self.state.side_effect = QueryError("Dataset not found.")
        response = self.client.get(f"/api/v1/investigation?{DB}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"]["code"], "invalid_query")

    def test_export_streams_every_row_in_column_order(self):
        query = MagicMock()
        patch.object(sources.mysql_investigation, "base", return_value=query).start()
        patch.object(sources.mysql_investigation, "count", return_value=2).start()
        patch.object(
            sources.mysql_investigation,
            "row_summary",
            side_effect=lambda row, _: dict(
                zip(
                    [
                        "id",
                        "timestamp",
                        "host",
                        "service",
                        "severity",
                        "detector",
                        "unit",
                        "score",
                        "run_id",
                        "version_id",
                        "message",
                    ],
                    row,
                    strict=True,
                )
            ),
        ).start()
        session = patch.object(sources.db, "session").start()
        session.execute.return_value = [
            ["DB-1", "t1", "h", "s", "High", "rule", "window", 0.5, 3, 4, "=cmd"],
            ["DB-2", "t2", "h", "s", "Low", "rule", "window", 0.1, 3, 4, "ok"],
        ]
        response = self.get("/api/v1/anomalies/export")
        lines = response.get_data(as_text=True).splitlines()
        self.assertEqual(
            lines[0], "id,timestamp,host,service,severity,detector,unit,score,run_id,version_id,message"
        )
        self.assertEqual(lines[1], "DB-1,t1,h,s,High,rule,window,0.5,3,4,'=cmd")  # formula neutralized
        self.assertEqual(response.headers["X-Result-Count"], "2")
        self.assertIn("mysql-anomalies.csv", response.headers["Content-Disposition"])

    def test_export_limit(self):
        patch.object(sources.mysql_investigation, "base", return_value=MagicMock()).start()
        patch.object(sources.mysql_investigation, "count", return_value=sources.EXPORT_LIMIT + 1).start()
        response = self.client.get(f"/api/v1/anomalies/export?{DB}")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json["error"]["code"], "export_limit")

    def test_dashboard_page_and_fragment(self):
        with patch("app.render_template", return_value="page") as render:
            self.assertEqual(self.client.get(f"/?{DB}").get_data(as_text=True), "page")
        self.assertEqual(render.call_args.args[0], "dashboard.html")
        # Fragments are JSON for both backends (the database backend used to return the HTML page).
        fragment = self.client.get(f"/?{DB}", headers={"X-Workspace-Fragment": "1"})
        self.assertEqual(fragment.json["mode"], "database")
        self.state.side_effect = QueryError("Dataset not found.")
        failed = self.client.get(f"/?{DB}", headers={"X-Workspace-Fragment": "1"})
        self.assertEqual((failed.status_code, failed.json["error"]["code"]), (400, "invalid_query"))


class DemoSourceRoutingTest(unittest.TestCase):
    def test_named_fixtures_never_reach_the_database_backend(self):
        app = create_app({"TESTING": True})
        with patch.object(sources.mysql_investigation, "state", side_effect=AssertionError("database used")):
            response = app.test_client().get("/api/v1/investigation?source=demo")
        self.assertEqual((response.status_code, response.json["mode"]), (200, "demo"))

    def test_source_selection(self):
        self.assertIs(sources.source_for({"source": "db-3"}), sources.DATABASE)
        for args in ({}, {"source": "demo"}, {"source": "partial"}, {"source": "DB-3"}):
            self.assertIs(sources.source_for(args), sources.DEMO)


if __name__ == "__main__":
    unittest.main()
