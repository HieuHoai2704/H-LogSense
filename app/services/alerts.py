"""Idempotent alert decisions and a bounded, opt-in SMTP outbox."""

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import os, smtplib, ssl

from sqlalchemy import select, exists
from sqlalchemy.orm import Session

from app.models import AnomalyOutput, DetectorRun, DetectionUnit, LogEvent
from app.domain import AlertRule, Alert, AlertDecision, AlertAudit, Notification

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
                select(AlertRule.id).where(
                    AlertRule.dataset_id == dataset_id, AlertRule.enabled == True
                )
            )
        )
    for rule_id in rules:
        while True:
            with Session(engine) as session, session.begin():
                rule = session.scalar(
                    select(AlertRule).where(AlertRule.id == rule_id).with_for_update()
                )
                if rule.detector_id is not None and rule.detector_id != run.detector_id:
                    break
                query = select(AnomalyOutput).where(
                    AnomalyOutput.dataset_id == dataset_id,
                    AnomalyOutput.run_id == run_id,
                    AnomalyOutput.priority.in_(
                        PRIORITIES[PRIORITIES.index(rule.min_priority) :]
                    ),
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
                        query.join(
                            DetectionUnit, DetectionUnit.id == AnomalyOutput.unit_id
                        )
                        .outerjoin(LogEvent, LogEvent.id == DetectionUnit.event_id)
                        .where(
                            (DetectionUnit.host == rule.host)
                            | (
                                (DetectionUnit.host == None)
                                & (LogEvent.host == rule.host)
                            )
                        )
                    )
                outputs = list(
                    session.scalars(query.order_by(AnomalyOutput.id).limit(500))
                )
                if not outputs:
                    break
                for output in outputs:
                    now = datetime.now(timezone.utc)
                    cooling = (
                        rule.last_alert_at is not None
                        and now - rule.last_alert_at
                        < timedelta(seconds=rule.cooldown_seconds)
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


def deliver_notifications(engine, *, smtp_factory=None):
    if os.environ.get("SMTP_ENABLED") != "1":
        return {"status": "disabled", "sent": 0}
    host = os.environ.get("SMTP_HOST")
    recipient = os.environ.get("SMTP_TO")
    sender = os.environ.get("SMTP_FROM")
    if (
        not host
        or not recipient
        or not sender
        or any("\n" in x or "\r" in x for x in (host, recipient, sender))
    ):
        raise ValueError("Valid SMTP host/from/to configuration required.")
    factory = smtp_factory or smtplib.SMTP
    sent = 0
    for _ in range(100):
        with Session(engine) as session, session.begin():
            now = datetime.now(timezone.utc)
            notification = session.scalar(
                select(Notification)
                .where(
                    Notification.state.in_(["pending", "retry"]),
                    Notification.attempts < 3,
                    Notification.next_attempt <= now,
                )
                .order_by(Notification.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if notification is None:
                break
            notification.attempts += 1
            try:
                message = EmailMessage()
                message["From"] = sender
                message["To"] = recipient
                message["Subject"] = "LogSense investigation alert " + str(
                    notification.alert_id
                )
                message["Message-ID"] = (
                    f"<logsense-alert-{notification.dataset_id}-{notification.alert_id}@local.invalid>"
                )
                message.set_content(
                    f"Alert {notification.alert_id}, dataset {notification.dataset_id}. Investigate the authorized evidence view. A detector signal is not a confirmed root cause."
                )
                with factory(
                    host, int(os.environ.get("SMTP_PORT", "587")), timeout=5
                ) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    if os.environ.get("SMTP_USER"):
                        smtp.login(
                            os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", "")
                        )
                    smtp.send_message(message)
                notification.state = "sent"
                notification.error_code = None
                sent += 1
            except (OSError, smtplib.SMTPException):
                notification.state = "failed" if notification.attempts >= 3 else "retry"
                notification.error_code = "smtp_failed"
                notification.next_attempt = now + timedelta(
                    seconds=60 * 2**notification.attempts
                )
    return {"status": "processed", "sent": sent}
