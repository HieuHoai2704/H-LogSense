"""Worker loop backoff and the notification outbox claim/send/record cycle (audit batch 4)."""

from datetime import datetime, timedelta, timezone
import smtplib
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import create_app
from app.domain import Notification
from app.extensions import mail
from app.services import alerts
from scripts.run.supervision import serve


class ServeLoopTest(unittest.TestCase):
    def test_database_outage_backs_off_and_recovers(self):
        outcomes = [
            OperationalError("SELECT 1", {}, Exception("down")),
            OperationalError("SELECT 1", {}, Exception("down")),
            True,
            KeyboardInterrupt(),
        ]
        sleeps = []

        def step():
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        with self.assertLogs("h_logsen.worker", "WARNING") as logs, self.assertRaises(KeyboardInterrupt):
            serve(step, sleep=sleeps.append)
        self.assertEqual(sleeps, [2.0, 4.0])  # exponential, never a crash
        self.assertTrue(all("OperationalError" in line and "down" not in line for line in logs.output))

    def test_once_mode_surfaces_the_error(self):
        def step():
            raise OperationalError("SELECT 1", {}, Exception("down"))

        with self.assertRaises(OperationalError):
            serve(step, once=True, sleep=lambda _: None)

    def test_reclaim_runs_at_start_and_then_on_an_interval(self):
        calls, steps = [], iter([False, False, KeyboardInterrupt()])
        now = [0.0]

        def step():
            value = next(steps)
            if isinstance(value, BaseException):
                raise value
            now[0] += 30
            return value

        with self.assertRaises(KeyboardInterrupt):
            serve(step, reclaim=lambda: calls.append(now[0]), sleep=lambda _: None, clock=lambda: now[0])
        self.assertEqual(calls, [0.0, 60.0])


class OutboxDispatchTest(unittest.TestCase):
    """SQLite stand-in for notification_outbox: exercises the transaction boundaries, not MySQL locking."""

    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.engine = create_engine("sqlite://")
        event.listen(
            self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=OFF")
        )
        Notification.__table__.create(self.engine)
        with Session(self.engine) as session, session.begin():
            session.add(
                Notification(
                    id=1,
                    dataset_id=7,
                    alert_id=11,
                    state="pending",
                    attempts=0,
                    next_attempt=datetime.now(timezone.utc) - timedelta(minutes=1),
                )
            )
        self.mail_state = mail.init_mail(
            {
                "MAIL_SERVER": "smtp.invalid",
                "MAIL_PORT": 587,
                "MAIL_USE_TLS": True,
                "MAIL_SUPPRESS_SEND": False,
            }
        )
        self.query = alerts.select(Notification).where(
            Notification.state.in_(["pending", "retry", "sending"]),
            Notification.attempts < 3,
            Notification.next_attempt <= datetime.now(timezone.utc),
        )  # same filter as deliver_notifications

    def dispatch(self, factory):
        with patch.object(alerts.Session, "begin", alerts.Session.begin):
            return alerts._dispatch_notifications(
                self.engine, self.mail_state, factory, "a@example.invalid", ["b@example.invalid"], self.query
            )

    def row(self):
        with Session(self.engine) as session:
            item = session.get(Notification, 1)
            return item.state, item.attempts, item.error_code

    def test_sent_once(self):
        smtp = MagicMock()
        self.assertEqual(self.dispatch(smtp)["sent"], 1)
        self.assertEqual(self.row(), ("sent", 1, None))

    def test_rendering_error_is_counted_not_a_poison_row(self):
        with patch.object(
            alerts, "notification_message", side_effect=UnicodeEncodeError("utf-8", "x", 0, 1, "bad")
        ):
            self.dispatch(MagicMock())
        self.assertEqual(self.row(), ("failed", 1, "message_failed"))

    def test_smtp_failure_is_retried_later_with_the_attempt_kept(self):
        smtp = MagicMock(side_effect=smtplib.SMTPServerDisconnected("down"))
        self.dispatch(smtp)
        self.assertEqual(self.row(), ("retry", 1, "smtp_failed"))


if __name__ == "__main__":
    unittest.main()
