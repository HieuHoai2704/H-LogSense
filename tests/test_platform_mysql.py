"""Actual MySQL platform/API/auth/incident/window-model integration tests."""

from datetime import datetime, timedelta, timezone
import json, os, smtplib, unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

import test_mysql_integration as baseline

LINE, NOW = baseline.LINE, baseline.NOW
from app.models import AnomalyOutput, ProcessingJob, DetectorRun
from app.domain import User, UserDataset, AlertRule, Notification, DetectionPrediction, EvaluationReport
from app.services.bgl_ingestion import ingest_bgl
from app.services.detection import detect
from app.services.window_detection import aggregate_windows, template, run_windows
from app.services.alerts import generate_alerts, deliver_notifications


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "MySQL platform integration NOT RUN",
)
class PlatformMySQLTests(unittest.TestCase):
    setUpClass = classmethod(baseline.MySQLIntegrationTests.setUpClass.__func__)
    tearDown = baseline.MySQLIntegrationTests.tearDown
    event = baseline.MySQLIntegrationTests.event
    unit = baseline.MySQLIntegrationTests.unit
    make_run = baseline.MySQLIntegrationTests.make_run
    zipped = baseline.MySQLIntegrationTests.zipped

    def setUp(self):
        baseline.MySQLIntegrationTests.setUp(self)
        from app.security import attempts

        attempts.clear()
        self.app.config["SECRET_KEY"] = "synthetic-integration-session-secret"
        self.client = self.app.test_client()

    def login(self, role="admin", *, grant=True):
        with Session(self.engine) as session, session.begin():
            user = User(
                username=uuid4().hex,
                password_hash=generate_password_hash("synthetic-password-123"),
                role=role,
            )
            session.add(user)
            session.flush()
            user_id = user.id
            username = user.username
            if grant:
                session.add(UserDataset(user_id=user.id, dataset_id=self.dataset_id))
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "synthetic-password-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.csrf = response.json["csrf_token"]
        return user_id

    def headers(self):
        return {"X-CSRF-Token": self.csrf}

    def log_url(self, **extra):
        from urllib.parse import urlencode

        values = {
            "dataset_id": self.dataset_id,
            "start_time": NOW.isoformat(),
            "end_time": (NOW + timedelta(hours=1)).isoformat(),
        }
        values.update(extra)
        return "/api/v1/logs?" + urlencode(values)

    def seed_events(self, n=4):
        with self.session.begin():
            for i in range(n):
                event = self.event(self.session, timestamp=NOW + timedelta(seconds=i))
                event.host = "host-a" if i % 2 == 0 else "host-b"
                event.severity = "ERROR" if i % 2 == 0 else "INFO"
                event.message = "=formula %_" if i == 0 else "ordinary text"

    def test_01_login_logout_rbac(self):
        self.assertEqual(self.client.get("/api/v1/logs/datasets").status_code, 403)
        self.login("viewer")
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)
        self.assertEqual(
            self.client.post("/api/v1/detection/jobs", json={}, headers=self.headers()).status_code,
            403,
        )
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 403)
        self.assertEqual(
            self.client.post("/api/v1/auth/logout", headers=self.headers()).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 403)

    def test_02_invalid_login_rate_limit_and_json(self):
        self.assertEqual(self.client.post("/api/v1/auth/login", json=["bad"]).status_code, 401)
        for _ in range(5):
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/login",
                    json={"username": "missing", "password": "wrong"},
                ).status_code,
                401,
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login", json={"username": "missing", "password": "wrong"}
            ).status_code,
            429,
        )

    def test_03_logs_filters_timeline_and_csv_same_snapshot(self):
        self.seed_events()
        self.login()
        url = self.log_url(host="host-a", severity="ERROR", q="%_", limit=1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["count"], 1)
        token = response.json["scope_token"]
        scope = url + "&scope_token=" + token
        timeline = self.client.get(scope.replace("/logs?", "/logs/timeline?"))
        self.assertEqual(timeline.status_code, 200)
        self.assertEqual(timeline.json["count"], 1)
        csv = self.client.get(scope.replace("/logs?", "/logs/export?"))
        self.assertEqual(csv.status_code, 200)
        self.assertEqual(csv.headers["X-Result-Count"], "1")
        self.assertIn("'=formula %_", csv.text)
        self.assertEqual(sum(c["event_count"] for c in timeline.json["bins"]), 1)

    def test_04_keyset_no_duplicate_and_snapshot_excludes_append(self):
        self.seed_events(4)
        self.login()
        url = self.log_url(limit=2, sort="asc")
        first = self.client.get(url).json
        with self.session.begin():
            self.event(self.session, timestamp=NOW + timedelta(seconds=2))
        second = self.client.get(
            url + "&scope_token=" + first["scope_token"] + "&cursor=" + first["next_cursor"]
        ).json
        self.assertEqual(second["count"], 4)
        self.assertFalse(set(r["id"] for r in first["items"]) & set(r["id"] for r in second["items"]))
        self.assertEqual(self.client.get(url).json["count"], 5)
        self.assertEqual(
            self.client.get(url + "&host=other&scope_token=" + first["scope_token"]).status_code,
            400,
        )

    def test_05_validation_isolation_and_empty(self):
        self.login()
        self.assertEqual(self.client.get(self.log_url(dataset_id=self.other_id)).status_code, 403)
        for change in (
            {"limit": 0},
            {"sort": "bad"},
            {"start_time": "2026-11-04"},
            {"q": "x" * 201},
        ):
            self.assertEqual(self.client.get(self.log_url(**change)).status_code, 400)
        response = self.client.get(self.log_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["count"], 0)

    def test_06_raw_provenance_and_scope(self):
        self.seed_events(1)
        self.login()
        page = self.client.get(self.log_url()).json
        event_id = page["items"][0]["id"]
        url = self.log_url().replace("/logs?", f"/logs/{event_id}?") + "&scope_token=" + page["scope_token"]
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["raw"]["text"], LINE.decode())
        self.assertEqual(response.json["provenance"]["physical_line"], 1)
        self.assertEqual(self.client.get(url + "&host=wrong").status_code, 400)

    def rule_run(self):
        path = self.zipped(LINE.replace(b"INFO", b"ERROR") * 3)
        ingest_bgl(self.engine, self.dataset_id, path)
        return detect(self.engine, self.dataset_id)["run_id"]

    def test_07_anomaly_center_consistent_scope_and_evidence(self):
        run_id = self.rule_run()
        self.login()
        url = f"/api/v1/investigation?source=db-{self.dataset_id}&limit=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text[:1000])
        data = response.json
        self.assertEqual(data["scope_count"], 3)
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(sum(c["count"] for c in data["timeline"]["overall"]), 3)
        from werkzeug.datastructures import MultiDict
        from urllib.parse import urlencode

        params = MultiDict()
        for k, v in data["state"].items():
            for x in v if isinstance(v, list) else [v]:
                params.add(k, x)
        selection = next(c for c in data["timeline"]["overall"] if c["count"])
        params.setlist("selection_start", [selection["start"]])
        params.setlist("selection_end", [selection["end"]])
        selected = self.client.get("/api/v1/investigation?" + urlencode(list(params.items(multi=True)))).json
        export = self.client.get("/api/v1/anomalies/export?" + urlencode(list(params.items(multi=True))))
        self.assertEqual(int(export.headers["X-Result-Count"]), selected["result_count"])
        identity = data["events"][0]["id"]
        evidence = self.client.get(
            f"/api/v1/anomalies/{identity}/evidence?" + urlencode(list(params.items(multi=True)))
        )
        self.assertEqual(evidence.status_code, 200, evidence.text[:1000])
        self.assertEqual(evidence.json["mode"], "database")
        self.assertEqual(
            evidence.json["raw_event"]["page"]["text"],
            LINE.replace(b"INFO", b"ERROR").decode(),
        )
        from app.models import DetectorVersion

        run = self.session.get(DetectorRun, run_id)
        self.assertEqual(
            evidence.json["detector_evidence"]["rule_version"],
            self.session.get(DetectorVersion, run.version_id).version,
        )
        self.session.rollback()

    def test_08_latest_runs_prevent_replay_double_count(self):
        self.rule_run()
        detect(self.engine, self.dataset_id)
        self.login()
        data = self.client.get(f"/api/v1/investigation?source=db-{self.dataset_id}").json
        self.assertEqual(data["scope_count"], 3)
        self.assertEqual(len(data["state"]["run_id"]), 1)

    def test_09_alert_cooldown_idempotency_and_email_mock(self):
        run_id = self.rule_run()
        with self.session.begin():
            self.session.add(
                AlertRule(
                    dataset_id=self.dataset_id,
                    name="Test priority rule",
                    min_priority="High",
                    cooldown_seconds=300,
                )
            )
        result = generate_alerts(self.engine, self.dataset_id, run_id)
        self.assertEqual(result, {"created": 1, "suppressed": 2})
        self.assertEqual(
            generate_alerts(self.engine, self.dataset_id, run_id),
            {"created": 0, "suppressed": 0},
        )
        from flask_mail import Mail

        blocked_transport = MagicMock()
        with self.app.app_context(), patch.dict(os.environ, {"SMTP_ENABLED": "1", "MAIL_SUPPRESS_SEND": "1"}):
            with Mail().record_messages() as messages:
                preview = deliver_notifications(self.engine, smtp_factory=blocked_transport)
        self.assertEqual(preview, {"status": "suppressed", "sent": 0, "captured": 1})
        blocked_transport.assert_not_called()
        self.assertIn("<h1>H-logsen investigation alert</h1>", messages[0].html)
        with self.app.app_context():
            self.assertIn(b"alert-reference.csv", messages[0].as_bytes())
        with Session(self.engine) as session:
            pending = session.scalar(select(Notification).where(Notification.dataset_id == self.dataset_id))
            self.assertEqual((pending.state, pending.attempts), ("pending", 0))
        smtp = MagicMock()
        with patch.dict(
            os.environ,
            {
                "SMTP_ENABLED": "1",
                "SMTP_HOST": "smtp.invalid",
                "SMTP_FROM": "test@example.invalid",
                "SMTP_TO": "analyst@example.invalid",
            },
        ):
            delivered = deliver_notifications(self.engine, smtp_factory=smtp)
        self.assertEqual(delivered["sent"], 1)
        smtp.return_value.starttls.assert_called_once()
        smtp.return_value.sendmail.assert_called_once()
        self.assertEqual(deliver_notifications(self.engine), {"status": "disabled", "sent": 0})

    def test_10_incident_rbac_csrf_status_notes_and_history(self):
        run_id = self.rule_run()
        with self.session.begin():
            self.session.add(
                AlertRule(
                    dataset_id=self.dataset_id,
                    name="Incident rule",
                    min_priority="High",
                    cooldown_seconds=300,
                )
            )
        generate_alerts(self.engine, self.dataset_id, run_id)
        self.login("analyst")
        listing = self.client.get(f"/api/v1/alerts?dataset_id={self.dataset_id}")
        self.assertEqual(listing.status_code, 200)
        alert_id = listing.json["items"][0]["id"]
        url = f"/api/v1/alerts/{alert_id}"
        self.assertEqual(self.client.patch(url, json={"status": "acknowledged"}).status_code, 403)
        result = self.client.patch(
            url,
            json={"status": "acknowledged", "note": "password=synthetic-value"},
            headers=self.headers(),
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["status"], "acknowledged")
        self.assertNotIn("synthetic-value", json.dumps(result.json["history"]))
        self.assertEqual(
            self.client.patch(url, json={"status": "open"}, headers=self.headers()).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/alert-rules",
                json={"dataset_id": self.dataset_id},
                headers=self.headers(),
            ).status_code,
            403,
        )

    def test_11_email_retry_bounded(self):
        run_id = self.rule_run()
        with self.session.begin():
            self.session.add(
                AlertRule(
                    dataset_id=self.dataset_id,
                    name="Retry rule",
                    min_priority="High",
                    cooldown_seconds=300,
                )
            )
        generate_alerts(self.engine, self.dataset_id, run_id)
        smtp = MagicMock(side_effect=smtplib.SMTPException("Synthetic failure"))
        with patch.dict(
            os.environ,
            {
                "SMTP_ENABLED": "1",
                "SMTP_HOST": "smtp.invalid",
                "SMTP_FROM": "test@example.invalid",
                "SMTP_TO": "analyst@example.invalid",
            },
        ):
            for _ in range(3):
                with self.session.begin():
                    for item in self.session.scalars(
                        select(Notification).where(Notification.dataset_id == self.dataset_id)
                    ):
                        item.next_attempt = NOW - timedelta(days=365)
                deliver_notifications(self.engine, smtp_factory=smtp)
        with self.session.begin():
            item = self.session.scalar(select(Notification).where(Notification.dataset_id == self.dataset_id))
            self.assertEqual((item.attempts, item.state), (3, "failed"))

    def window_source(self):
        lines = []
        for window in range(96):
            stamp = datetime(2005, 6, 3, tzinfo=timezone.utc) + timedelta(minutes=window * 5)
            epoch = str(int(stamp.timestamp())).encode()
            for _ in range(40 if window >= 80 else window % 5 + 1):
                raw = LINE.replace(b"1117838570", epoch)
                if window >= 80:
                    raw = raw.replace(b"- ", b"TESTALERT ", 1).replace(b"INFO", b"ERROR")
                lines.append(raw)
        return self.zipped(b"".join(lines))

    def test_12_window_features_deterministic_no_labels(self):
        rows = [
            SimpleNamespace(id=i, timestamp=NOW, host="host", severity="INFO", message=f"value {i}")
            for i in range(4)
        ]
        first = list(aggregate_windows(rows))
        self.assertEqual(first, list(aggregate_windows(rows)))
        self.assertEqual(template("value 1"), template("value 2"))
        self.assertEqual(first[0]["count"], 4)
        self.assertNotIn("label", first[0])

    def test_13_window_rule_predictions_retry_evaluation(self):
        ingest_bgl(self.engine, self.dataset_id, self.window_source())
        first = run_windows(self.engine, self.dataset_id, "test-window-rule", {"detector": "rule"})
        again = run_windows(self.engine, self.dataset_id, "test-window-rule", {"detector": "rule"})
        self.assertEqual(first["run_id"], again["run_id"])
        with self.session.begin():
            report = self.session.scalar(
                select(EvaluationReport).where(EvaluationReport.run_id == first["run_id"])
            )
            self.assertEqual(report.metrics["unit"], "observed host-window")
            self.assertGreater(report.metrics["eligible_units"], 0)
            self.assertIsNotNone(report.metrics["auprc_average_precision"])
            self.assertEqual(
                self.session.scalar(
                    select(func.count())
                    .select_from(DetectionPrediction)
                    .where(DetectionPrediction.run_id == first["run_id"])
                ),
                report.metrics["eligible_units"],
            )

    def test_14_job_submission_idempotency_and_worker(self):
        ingest_bgl(self.engine, self.dataset_id, self.window_source())
        self.login("analyst")
        body = {
            "dataset_id": self.dataset_id,
            "idempotency_key": "window-job",
            "configuration": {"detector": "isolation_forest"},
        }
        first = self.client.post("/api/v1/detection/jobs", json=body, headers=self.headers())
        self.assertEqual(first.status_code, 202)
        self.assertEqual(
            self.client.post("/api/v1/detection/jobs", json=body, headers=self.headers()).json["job_id"],
            first.json["job_id"],
        )
        body["configuration"] = {"detector": "rule"}
        self.assertEqual(
            self.client.post("/api/v1/detection/jobs", json=body, headers=self.headers()).status_code,
            409,
        )
        from scripts.run.worker import run_once

        self.assertTrue(run_once(self.engine))
        status = self.client.get("/api/v1/detection/jobs/" + str(first.json["job_id"]))
        self.assertEqual(status.json["state"], "completed", status.json)

    def test_15_upload_requires_auth_and_unrelated_size_limit(self):
        self.assertEqual(self.client.post("/api/v1/uploads", data=b"test").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                data=b"x" * (1024 * 1024 + 1),
                content_type="application/json",
            ).status_code,
            413,
        )

    def test_16_manager_rule_creation_and_invalid_assignment(self):
        self.login("manager")
        response = self.client.post(
            "/api/v1/alert-rules",
            json={
                "dataset_id": self.dataset_id,
                "name": "Actual API rule",
                "min_priority": "Critical",
                "cooldown_seconds": 60,
            },
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.client.post(
                "/api/v1/alert-rules",
                json={"dataset_id": self.other_id, "name": "Forbidden"},
                headers=self.headers(),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/v1/alert-rules", json=["invalid"], headers=self.headers()).status_code,
            400,
        )

    def test_17_invalid_window_request_rejected_before_queue(self):
        self.login("analyst")
        body = {
            "dataset_id": self.dataset_id,
            "idempotency_key": "invalid-time",
            "configuration": {"start_time": "2026-01-01"},
        }
        self.assertEqual(
            self.client.post("/api/v1/detection/jobs", json=body, headers=self.headers()).status_code,
            400,
        )

    def test_18_window_model_deterministic_scores(self):
        ingest_bgl(self.engine, self.dataset_id, self.window_source())
        first = run_windows(
            self.engine,
            self.dataset_id,
            "if-seed-a",
            {"detector": "isolation_forest", "seed": 42},
        )
        second = run_windows(
            self.engine,
            self.dataset_id,
            "if-seed-b",
            {"detector": "isolation_forest", "seed": 42},
        )
        with self.session.begin():
            values = []
            for result in (first, second):
                values.append(
                    self.session.execute(
                        select(DetectionPrediction.score, DetectionPrediction.predicted)
                        .where(
                            DetectionPrediction.dataset_id == self.dataset_id,
                            DetectionPrediction.run_id == result["run_id"],
                        )
                        .order_by(DetectionPrediction.unit_id)
                    ).all()
                )
            self.assertEqual(values[0], values[1])

    def test_19_failed_job_requeue_and_active_worker_guard(self):
        self.login("analyst")
        with self.session.begin():
            job = ProcessingJob(
                dataset_id=self.dataset_id,
                kind="analysis",
                state="failed",
                job_key="recover",
                configuration={"detector": "rule"},
            )
            self.session.add(job)
            self.session.flush()
            job_id = job.id
        url = "/api/v1/detection/jobs/" + str(job_id) + "/retry"
        from app.services.bgl_ingestion import import_lease

        with import_lease(self.engine, "analysis-job-" + str(job_id)):
            self.assertEqual(self.client.post(url, headers=self.headers()).status_code, 409)
        self.assertEqual(self.client.post(url, headers=self.headers()).status_code, 202)
        self.assertEqual(self.client.post(url, headers=self.headers()).status_code, 409)

    def test_20_log_bin_exact_microsecond_boundary(self):
        with self.session.begin():
            self.event(self.session, timestamp=NOW + timedelta(minutes=1, microseconds=-1))
            self.event(self.session, timestamp=NOW + timedelta(minutes=1))
            self.event(self.session, timestamp=NOW + timedelta(hours=1))
        self.login()
        result = self.client.get(self.log_url().replace("/logs?", "/logs/timeline?") + "&bins=60")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["count"], 2)
        self.assertEqual([b["event_count"] for b in result.json["bins"][:2]], [1, 1])

    def test_21_anomaly_bin_exact_boundary(self):
        with self.session.begin():
            run = self.make_run(self.session)
            for offset in (timedelta(minutes=5, microseconds=-1), timedelta(minutes=5)):
                unit = self.unit(self.session, self.event(self.session, timestamp=NOW + offset))
                self.session.add(
                    AnomalyOutput(
                        dataset_id=self.dataset_id,
                        run_id=run.id,
                        unit_id=unit.id,
                        anchor_time=unit.start_time,
                        priority="High",
                        evidence={},
                    )
                )
        self.login()
        from urllib.parse import urlencode

        params = {
            "source": "db-" + str(self.dataset_id),
            "start_time": NOW.isoformat(),
            "end_time": (NOW + timedelta(hours=1)).isoformat(),
            "resolution": "300",
        }
        result = self.client.get("/api/v1/investigation?" + urlencode(params))
        self.assertEqual(result.status_code, 200, result.text[:1000])
        self.assertEqual([b["count"] for b in result.json["timeline"]["overall"][:2]], [1, 1])

    def test_22_mysql_presets_use_observed_end_and_custom_validates(self):
        self.rule_run()
        self.login()
        result = self.client.get(f"/api/v1/investigation?source=db-{self.dataset_id}&range=6h")
        self.assertEqual(result.status_code, 200)
        state = result.json["state"]
        parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
        self.assertEqual(parse(state["end_time"]) - parse(state["start_time"]), timedelta(hours=6))
        self.assertEqual(state["range"], "6h")
        self.assertEqual(
            self.client.get(f"/api/v1/investigation?source=db-{self.dataset_id}&range=custom").status_code,
            400,
        )
