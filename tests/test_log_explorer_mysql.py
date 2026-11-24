"""Log Explorer endpoints on real MySQL: search syntax, facets, level timeline, patterns, insights,
surrounding logs and saved views."""

from datetime import timedelta
import os
import unittest
from urllib.parse import urlencode

from sqlalchemy.orm import Session
import test_platform_mysql as platform

NOW = platform.NOW


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Log Explorer MySQL integration NOT RUN",
)
class LogExplorerMySQLTests(unittest.TestCase):
    setUpClass = classmethod(platform.PlatformMySQLTests.setUpClass.__func__)
    setUp = platform.PlatformMySQLTests.setUp
    tearDown = platform.PlatformMySQLTests.tearDown
    event = platform.PlatformMySQLTests.event
    login = platform.PlatformMySQLTests.login
    headers = platform.PlatformMySQLTests.headers

    def seed(self):
        """Ten minutes of logs on two hosts with a burst of new errors in the last minutes."""
        rows = []
        for i in range(60):
            rows.append(
                (i * 10, "R02-M1-N0" if i % 2 else "R03-M0-N1", "KERNEL", "INFO", f"generating core.{i}")
            )
        for i in range(6):
            rows.append(
                (520 + i * 5, "R02-M1-N0", "APP", "ERROR", f"ciod: failed to read message prefix on 0x{i:x}")
            )
        rows.append((30, None, None, "WARNING", "instruction cache parity error corrected"))
        with Session(self.engine) as session, session.begin():
            ids = []
            for offset, host, service, severity, message in rows:
                event = self.event(session, timestamp=NOW + timedelta(seconds=offset))
                event.host, event.service, event.severity, event.message = host, service, severity, message
                ids.append(event.id)
        return ids

    def url(self, path, **extra):
        values = {
            "dataset_id": self.dataset_id,
            "start_time": NOW.isoformat(),
            "end_time": (NOW + timedelta(minutes=10)).isoformat(),
        }
        values.update(extra)
        return path + "?" + urlencode(values)

    def get(self, path, **extra):
        response = self.client.get(self.url(path, **extra))
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_01_search_syntax_filters_and_excludes(self):
        self.seed()
        self.login("staff")
        count = lambda query: self.get("/api/v1/logs", query=query)["count"]  # noqa: E731
        self.assertEqual(count(""), 67)
        self.assertEqual(count("level:error"), 6)
        self.assertEqual(count("-level:INFO"), 7)
        self.assertEqual(count("host:R02-M1*"), 36)
        self.assertEqual(count("host:R02-M1* -service:KERNEL"), 6)
        self.assertEqual(count('"message prefix" -0x5'), 5)
        self.assertEqual(count("-host:R02-M1-N0"), 31)  # includes the event without a host
        self.assertEqual(count("service:APP level:ERROR prefix"), 6)
        self.assertEqual(count("%_"), 0)  # LIKE wildcards are literal
        # The page, the timeline and the export agree on the same scope.
        timeline = self.get("/api/v1/logs/timeline", query="-level:INFO")
        self.assertEqual(timeline["count"], 7)
        self.assertEqual(sum(cell["levels"].get("ERROR", 0) for cell in timeline["bins"]), 6)
        self.assertEqual(sum(cell["levels"].get("WARNING", 0) for cell in timeline["bins"]), 1)
        self.assertEqual(self.client.get(self.url("/api/v1/logs", query="x" * 501)).status_code, 400)

    def test_02_facets_count_the_current_scope(self):
        self.seed()
        self.login("staff")
        facets = self.get("/api/v1/logs/facets")["facets"]
        self.assertEqual(facets["level"]["values"][0], {"value": "INFO", "count": 60})
        self.assertEqual(
            {v["value"]: v["count"] for v in facets["host"]["values"]},
            {
                "R02-M1-N0": 36,
                "R03-M0-N1": 30,
                None: 1,
            },
        )
        self.assertEqual(facets["service"]["distinct"], 2)
        narrowed = self.get("/api/v1/logs/facets", query="level:ERROR")["facets"]
        self.assertEqual(narrowed["host"]["values"], [{"value": "R02-M1-N0", "count": 6}])

    def test_03_patterns_group_variable_tokens(self):
        self.seed()
        self.login("staff")
        data = self.get("/api/v1/logs/patterns")
        self.assertFalse(data["truncated"])
        self.assertEqual(data["scanned"], 67)
        top = data["patterns"][0]
        self.assertEqual(
            (top["pattern"], top["count"], top["levels"]), ("generating core.<*>", 60, {"INFO": 60})
        )
        errors = next(p for p in data["patterns"] if p["levels"] == {"ERROR": 6})
        self.assertEqual(errors["pattern"], "ciod: failed to read message prefix on <*>")
        self.assertEqual(errors["filter_terms"], ["ciod: failed to read message prefix on"])
        # The pattern's terms find exactly its events.
        query = " ".join(f'"{term}"' for term in errors["filter_terms"])
        self.assertEqual(self.get("/api/v1/logs", query=query)["count"], 6)

    def test_04_insights_spike_new_pattern_and_anomalies(self):
        self.seed()
        self.login("staff")
        data = self.get("/api/v1/logs/insights")
        self.assertEqual(data["new_patterns"][0]["pattern"], "ciod: failed to read message prefix on <*>")
        self.assertTrue(data["new_patterns_checked"])
        self.assertEqual(data["detector_anomalies"], {"total": 0, "by_priority": {}})
        self.assertEqual(data["investigation"]["source"], f"db-{self.dataset_id}")
        self.assertEqual(data["error_spikes"], [])  # six errors stay under the minimum of ten

    def test_05_surrounding_logs_same_host_regardless_of_filters(self):
        ids = self.seed()
        self.login("staff")
        target = ids[61]  # the second error, host R02-M1-N0
        page = self.get("/api/v1/logs", query="level:ERROR")
        context = self.client.get(
            self.url(
                f"/api/v1/logs/{target}/context", query="level:ERROR", scope_token=page["scope_token"], size=3
            )
        ).json
        self.assertEqual(context["event"]["id"], target)
        self.assertEqual(len(context["before"]), 3)
        self.assertEqual(len(context["after"]), 3)
        self.assertTrue(all(row["host"] == "R02-M1-N0" for row in context["before"] + context["after"]))
        self.assertIn("INFO", {row["severity"] for row in context["before"]})  # not limited by level:ERROR
        stamps = [row["timestamp"] for row in context["before"]] + [context["event"]["timestamp"]]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(self.client.get(self.url("/api/v1/logs/999999999/context")).status_code, 404)

    def test_06_saved_views_per_account_with_csrf(self):
        self.login("staff")
        self.assertEqual(self.client.get("/api/v1/logs/views").json, {"views": []})
        view = {
            "name": "Errors on R02",
            "params": {"dataset_id": str(self.dataset_id), "query": "level:ERROR"},
        }
        self.assertEqual(self.client.post("/api/v1/logs/views", json=view).status_code, 403)  # no CSRF header
        saved = self.client.post("/api/v1/logs/views", json=view, headers=self.headers())
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(saved.json["views"], [view])
        for bad in ({"name": "", "params": {"q": "x"}}, {"name": "x", "params": {"password": "y"}}, ["x"]):
            self.assertEqual(
                self.client.post("/api/v1/logs/views", json=bad, headers=self.headers()).status_code, 400
            )
        mine, my_csrf = self.client, self.csrf
        self.client = self.app.test_client()
        self.login("staff")
        self.assertEqual(self.client.get("/api/v1/logs/views").json, {"views": []})  # per account
        self.client, self.csrf = mine, my_csrf
        deleted = self.client.delete("/api/v1/logs/views?name=Errors+on+R02", headers=self.headers())
        self.assertEqual(deleted.json, {"views": []})
        self.assertEqual(
            self.client.delete("/api/v1/logs/views?name=missing", headers=self.headers()).status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
