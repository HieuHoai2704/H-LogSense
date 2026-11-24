"""Authentication, evaluation and incident domain tables."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Model
from app.models import Identity, Scoped, UTCDateTime, options, scoped_fk


def now():
    return datetime.now(timezone.utc)


class User(Identity, Model):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username"),
        UniqueConstraint("email"),
        CheckConstraint("role IN ('staff','admin')", name="role"),
        options(),
    )
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))  # optional; required for self-registration
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    saved_log_views: Mapped[list | None] = mapped_column(JSON)  # named Log Explorer filters


class UserDataset(Identity, Model):
    __tablename__ = "user_datasets"
    __table_args__ = (UniqueConstraint("user_id", "dataset_id"), options())
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), nullable=False)


class DetectionPrediction(Scoped, Model):
    __tablename__ = "detection_predictions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "run_id", "unit_id"),
        scoped_fk("run_id", "detector_runs", "fk_prediction_run"),
        scoped_fk("unit_id", "detection_units", "fk_prediction_unit"),
        options(),
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    score: Mapped[float] = mapped_column(DOUBLE(asdecimal=False), nullable=False)
    predicted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    features: Mapped[dict] = mapped_column(JSON, nullable=False)


class EvaluationReport(Scoped, Model):
    __tablename__ = "evaluation_reports"
    __table_args__ = (
        UniqueConstraint("dataset_id", "run_id"),
        scoped_fk("run_id", "detector_runs", "fk_evaluation_run"),
        options(),
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)


class AlertRule(Scoped, Model):
    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        CheckConstraint("cooldown_seconds >= 0 AND cooldown_seconds <= 86400", name="cooldown"),
        CheckConstraint("min_priority IN ('Low','Medium','High','Critical')", name="priority"),
        options(),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    detector_id: Mapped[int | None] = mapped_column(ForeignKey("detectors.id"))
    min_priority: Mapped[str] = mapped_column(String(16), nullable=False)
    host: Mapped[str | None] = mapped_column(String(128))
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_alert_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Alert(Scoped, Model):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "rule_id", "anomaly_id"),
        scoped_fk("rule_id", "alert_rules", "fk_alert_rule"),
        ForeignKeyConstraint(
            ["dataset_id", "anomaly_id", "run_id"],
            [
                "anomaly_outputs.dataset_id",
                "anomaly_outputs.id",
                "anomaly_outputs.run_id",
            ],
            name="fk_alert_anomaly_run",
        ),
        CheckConstraint(
            "status IN ('open','acknowledged','investigating','resolved')",
            name="status",
        ),
        options(),
    )
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anomaly_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now)


class AlertAudit(Scoped, Model):
    __tablename__ = "alert_audit"
    __table_args__ = (scoped_fk("alert_id", "alerts", "fk_audit_alert"), options())
    alert_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now)


class Notification(Scoped, Model):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("dataset_id", "alert_id"),
        scoped_fk("alert_id", "alerts", "fk_notification_alert"),
        CheckConstraint("attempts >= 0 AND attempts <= 3", name="attempts"),
        CheckConstraint("state IN ('pending','retry','sending','sent','failed')", name="state"),
        Index("ix_notification_outbox_state_next_attempt_id", "state", "next_attempt", "id"),
        options(),
    )
    alert_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=now)
    error_code: Mapped[str | None] = mapped_column(String(32))


class AlertDecision(Scoped, Model):
    __tablename__ = "alert_decisions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "rule_id", "anomaly_id"),
        scoped_fk("rule_id", "alert_rules", "fk_decision_rule"),
        scoped_fk("anomaly_id", "anomaly_outputs", "fk_decision_anomaly"),
        CheckConstraint("outcome IN ('alerted','cooldown')", name="outcome"),
        options(),
    )
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anomaly_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
