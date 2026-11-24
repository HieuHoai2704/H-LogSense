"""Idempotent alert decisions and a bounded, opt-in SMTP outbox."""

from contextlib import nullcontext, suppress
from datetime import datetime, timedelta, timezone
import logging
import os
import smtplib
import ssl

from flask import Flask, current_app, has_app_context, render_template
from flask_mail import Connection, Message
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.domain import Alert, AlertAudit, AlertDecision, AlertRule, Notification
from app.extensions import mail
from app.models import AnomalyOutput, DetectionUnit, DetectorRun, LogEvent
from config import APP_NAME

log = logging.getLogger("h_logsen.alerts")
# A claimed notification is retried if the dispatcher dies before recording the result.
CLAIM_SECONDS = 600

PRIORITIES = ["Low", "Medium", "High", "Critical"]


def generate_alerts(engine, dataset_id, run_id):
    created = suppressed = 0
    with Session(engine) as session:
        run = session.scalar(
            select(DetectorRun).where(
                DetectorRun.dataset_id == dataset_id,
                DetectorRun.id == run_id,
                DetectorRun.state == "completed",
            )
        )
        if run is None:
            raise ValueError("Completed scoped run required.")
        rules = list(
            session.scalars(
                select(AlertRule.id).where(AlertRule.dataset_id == dataset_id, AlertRule.enabled.is_(True))
            )
        )
    for rule_id in rules:
        while True:
            with Session(engine) as session, session.begin():
                rule = session.scalar(select(AlertRule).where(AlertRule.id == rule_id).with_for_update())
                if rule.detector_id is not None and rule.detector_id != run.detector_id:
                    break
                query = select(AnomalyOutput).where(
                    AnomalyOutput.dataset_id == dataset_id,
                    AnomalyOutput.run_id == run_id,
                    AnomalyOutput.priority.in_(PRIORITIES[PRIORITIES.index(rule.min_priority) :]),
                    ~exists(
                        select(AlertDecision.id).where(
                            AlertDecision.dataset_id == dataset_id,
                            AlertDecision.rule_id == rule_id,
                            AlertDecision.anomaly_id == AnomalyOutput.id,
                        )
                    ),
                )
                if rule.host:
                    query = (
                        query.join(DetectionUnit, DetectionUnit.id == AnomalyOutput.unit_id)
                        .outerjoin(LogEvent, LogEvent.id == DetectionUnit.event_id)
                        .where(
                            (DetectionUnit.host == rule.host)
                            | (DetectionUnit.host.is_(None) & (LogEvent.host == rule.host))
                        )
                    )
                outputs = list(session.scalars(query.order_by(AnomalyOutput.id).limit(500)))
                if not outputs:
                    break
                for output in outputs:
                    now = datetime.now(timezone.utc)
                    cooling = rule.last_alert_at is not None and now - rule.last_alert_at < timedelta(
                        seconds=rule.cooldown_seconds
                    )
                    session.add(
                        AlertDecision(
                            dataset_id=dataset_id,
                            rule_id=rule_id,
                            anomaly_id=output.id,
                            outcome="cooldown" if cooling else "alerted",
                        )
                    )
                    if cooling:
                        suppressed += 1
                        continue
                    alert = Alert(
                        dataset_id=dataset_id,
                        rule_id=rule_id,
                        anomaly_id=output.id,
                        run_id=run_id,
                    )
                    session.add(alert)
                    session.flush()
                    session.add(
                        AlertAudit(
                            dataset_id=dataset_id,
                            alert_id=alert.id,
                            action="created",
                            details={"anomaly_id": output.id, "run_id": run_id},
                        )
                    )
                    session.add(Notification(dataset_id=dataset_id, alert_id=alert.id))
                    rule.last_alert_at = now
                    created += 1
    return {"created": created, "suppressed": suppressed}


class VerifiedSMTPConnection(Connection):
    """Keep the outbox's timeout and certificate verification with Flask-Mail."""

    def __init__(self, mail_state, factory):
        super().__init__(mail_state)
        self.factory = factory

    def configure_host(self):
        host = self.factory(self.mail.server, self.mail.port, timeout=5)
        try:
            host.starttls(context=ssl.create_default_context())
            if self.mail.username:
                host.login(self.mail.username, self.mail.password or "")
        except Exception:
            host.close()
            raise
        return host

    def __exit__(self, *exc):
        if self.host is not None:
            with suppress(OSError, smtplib.SMTPException):
                self.host.quit()
            with suppress(OSError):
                self.host.close()


def notification_message(notification, sender, recipients):
    alert_id, dataset_id = notification.alert_id, notification.dataset_id
    message = Message(
        subject=f"{APP_NAME} investigation alert {alert_id}",
        sender=sender,
        recipients=recipients,
        body=f"Alert {alert_id}, dataset {dataset_id}. Review the evidence in {APP_NAME}.",
        html=render_template("mail/alert.html", app_name=APP_NAME, alert_id=alert_id, dataset_id=dataset_id),
    )
    message.msgId = f"<logsense-alert-{dataset_id}-{alert_id}@local.invalid>"
    message.attach("alert-reference.csv", "text/csv", f"dataset_id,alert_id\r\n{dataset_id},{alert_id}\r\n")
    return message


def deliver_notifications(engine, *, smtp_factory=None, alert_id=None):
    if os.environ.get("SMTP_ENABLED") != "1":
        return {"status": "disabled", "sent": 0}
    context = nullcontext()
    if not has_app_context():
        app = Flask("app")
        mail.init_app(app)
        context = app.app_context()
    with context:
        suppressed = bool(
            current_app.testing
            or current_app.config.get("MAIL_SUPPRESS_SEND")
            or os.environ.get("MAIL_SUPPRESS_SEND") == "1"
        )
        host = os.environ.get("SMTP_HOST", "")
        recipient = os.environ.get("SMTP_TO", "")
        sender = os.environ.get("SMTP_FROM", "")
        if any("\n" in x or "\r" in x for x in (host, recipient, sender)):
            raise ValueError("Invalid SMTP host or address.")
        recipients = [address.strip() for address in recipient.split(",") if address.strip()]
        if not suppressed and (not host or not recipients or not sender):
            raise ValueError("SMTP_HOST, SMTP_FROM and SMTP_TO are required for delivery.")
        sender = sender or "logsense@example.invalid"
        recipients = recipients or ["preview@example.invalid"]
        if len(recipients) > 20 or any("@" not in address for address in [sender, *recipients]):
            raise ValueError("Provide a sender and at most 20 recipient email addresses.")
        state = mail.init_mail(
            {
                "MAIL_SERVER": host,
                "MAIL_PORT": int(os.environ.get("SMTP_PORT", "587")),
                "MAIL_USERNAME": os.environ.get("SMTP_USER"),
                "MAIL_PASSWORD": os.environ.get("SMTP_PASSWORD"),
                "MAIL_USE_TLS": True,
                "MAIL_SUPPRESS_SEND": suppressed,
            }
        )
        query = (
            select(Notification)
            .where(
                Notification.state.in_(["pending", "retry", "sending"]),
                Notification.attempts < 3,
                Notification.next_attempt <= datetime.now(timezone.utc),
            )
            .order_by(Notification.id)
        )
        if alert_id is not None:
            query = query.where(Notification.alert_id == alert_id)
        return _dispatch_notifications(engine, state, smtp_factory or smtplib.SMTP, sender, recipients, query)


def _dispatch_notifications(engine, mail_state, factory, sender, recipients, query):
    if mail_state.suppress:
        with Session(engine) as session, VerifiedSMTPConnection(mail_state, factory) as connection:
            pending = session.scalars(query.limit(100))
            captured = 0
            for notification in pending:
                connection.send(notification_message(notification, sender, recipients))
                captured += 1
        return {"status": "suppressed", "sent": 0, "captured": captured}
    # A claim that expired after the last allowed attempt cannot be retried: close it.
    with Session(engine) as session, session.begin():
        for stale in session.scalars(
            select(Notification)
            .where(
                Notification.state == "sending",
                Notification.attempts >= 3,
                Notification.next_attempt <= datetime.now(timezone.utc),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        ):
            stale.state, stale.error_code = "failed", "delivery_unknown"
    sent = 0
    for _ in range(100):
        # 1. Claim and count the attempt in its own transaction, before any network I/O, so a
        #    failure while building or sending can never roll the counter back (no poison rows).
        with Session(engine) as session, session.begin():
            now = datetime.now(timezone.utc)
            notification = session.scalar(query.with_for_update(skip_locked=True).limit(1))
            if notification is None:
                break
            notification.attempts += 1
            notification.state = "sending"
            notification.next_attempt = now + timedelta(seconds=CLAIM_SECONDS)
            notification_id, attempts = notification.id, notification.attempts
            try:
                message = notification_message(notification, sender, recipients)
            except Exception:
                log.exception("notification %s could not be rendered", notification_id)
                message = None
        # 2. Send outside any database transaction: a commit failure can no longer resend mail.
        outcome, code = "sent", None
        if message is None:
            outcome, code = "failed", "message_failed"
        else:
            try:
                with VerifiedSMTPConnection(mail_state, factory) as connection:
                    connection.send(message)
            except (OSError, smtplib.SMTPException) as error:
                log.warning(
                    "notification %s: SMTP delivery failed (%s)", notification_id, type(error).__name__
                )
                outcome, code = "retry", "smtp_failed"
            except Exception:
                log.exception("notification %s could not be sent", notification_id)
                outcome, code = "failed", "message_failed"
        # 3. Record the outcome.
        with Session(engine) as session, session.begin():
            notification = session.get(Notification, notification_id)
            if outcome == "sent":
                notification.state, notification.error_code = "sent", None
                sent += 1
            elif outcome == "retry":
                notification.state = "failed" if attempts >= 3 else "retry"
                notification.error_code = code
                notification.next_attempt = now + timedelta(seconds=60 * 2**attempts)
            else:
                notification.state, notification.error_code = "failed", code
    return {"status": "processed", "sent": sent}
