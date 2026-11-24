"""MySQL foundation. Composite foreign keys enforce dataset ownership in SQL."""

from datetime import datetime, timezone
import math

from sqlalchemy import (
    BigInteger,
    String,
    JSON,
    Integer,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Computed,
    Index,
)
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT, LONGBLOB, DOUBLE
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, relationship, validates
from sqlalchemy.types import TypeDecorator

from app.extensions import db


class UTCDateTime(TypeDecorator):
    impl = DATETIME(fsp=6)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def options():
    return {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_as_cs",
    }


def scoped_fk(column, table, name):
    return ForeignKeyConstraint(
        ["dataset_id", column],
        [table + ".dataset_id", table + ".id"],
        name=name,
        ondelete="RESTRICT",
    )


class Identity:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class Scoped(Identity):
    @declared_attr
    def dataset_id(cls) -> Mapped[int]:
        return mapped_column(BigInteger, ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)


class DataSource(Identity, db.Model):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("source_key"), options())
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    datasets = relationship("Dataset", back_populates="source")


class Dataset(Identity, db.Model):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("source_id", "dataset_key"),
        CheckConstraint(
            "state IN ('registered','importing','partial','imported','failed','archived')",
            name="state",
        ),
        CheckConstraint("data_mode IN ('real','synthetic','unverified')", name="mode"),
        options(),
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="unverified")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="registered")
    input_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source = relationship("DataSource", back_populates="datasets")


class SourceArtifact(Scoped, db.Model):
    __tablename__ = "source_artifacts"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "artifact_key"),
        CheckConstraint(
            "byte_length >= 0 AND checkpoint_line >= 0 AND checkpoint_byte >= 0 AND checkpoint_byte <= byte_length AND parsed_count >= 0 AND malformed_count >= 0 AND parsed_count + malformed_count = checkpoint_line",
            name="checkpoint",
        ),
        options(),
    )
    artifact_key: Mapped[str] = mapped_column(String(200), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_length: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_line: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checkpoint_byte: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    parsed_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    malformed_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class RawLogRecord(Scoped, db.Model):
    __tablename__ = "raw_log_records"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "artifact_id", "line_number"),
        scoped_fk("artifact_id", "source_artifacts", "fk_raw_artifact_scope"),
        CheckConstraint("line_number > 0 AND byte_offset >= 0", name="position"),
        options(),
    )
    artifact_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    byte_offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Exact bytes including terminator; malformed UTF-8 must remain reproducible.
    raw_bytes: Mapped[bytes] = mapped_column(LONGBLOB, nullable=False)
    parse_error: Mapped[str | None] = mapped_column(String(64))


class LogEvent(Scoped, db.Model):
    __tablename__ = "log_events"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "raw_id", "parser_version", "emit_index"),
        scoped_fk("raw_id", "raw_log_records", "fk_event_raw_scope"),
        Index("ix_events_dataset_time_id", "dataset_id", "timestamp", "id"),
        Index("ix_events_dataset_host_time", "dataset_id", "host", "timestamp", "id"),
        options(),
    )
    raw_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    emit_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    raw_timestamp: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str | None] = mapped_column(String(128))
    service: Mapped[str | None] = mapped_column(String(128))
    severity: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)


class DetectionUnit(Scoped, db.Model):
    __tablename__ = "detection_units"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "unit_key"),
        scoped_fk("event_id", "log_events", "fk_unit_event_scope"),
        CheckConstraint(
            "(kind = 'event' AND event_id IS NOT NULL AND end_time IS NULL) OR (kind = 'window' AND event_id IS NULL AND end_time IS NOT NULL AND end_time > start_time) OR (kind IN ('block','session') AND event_id IS NULL AND (end_time IS NULL OR end_time > start_time))",
            name="bounds",
        ),
        options(),
    )
    unit_key: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    event_id: Mapped[int | None] = mapped_column(BigInteger)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime)
    host: Mapped[str | None] = mapped_column(String(128))
    definition: Mapped[dict | None] = mapped_column(JSON)


class UnitEvent(Scoped, db.Model):
    __tablename__ = "unit_events"
    __table_args__ = (
        UniqueConstraint("dataset_id", "unit_id", "event_id"),
        scoped_fk("unit_id", "detection_units", "fk_membership_unit_scope"),
        scoped_fk("event_id", "log_events", "fk_membership_event_scope"),
        options(),
    )
    unit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class GroundTruthLabel(Scoped, db.Model):
    __tablename__ = "ground_truth_labels"
    __table_args__ = (
        scoped_fk("event_id", "log_events", "fk_label_event_scope"),
        scoped_fk("unit_id", "detection_units", "fk_label_unit_scope"),
        UniqueConstraint("dataset_id", "event_id", "source", "version"),
        UniqueConstraint("dataset_id", "unit_id", "source", "version"),
        CheckConstraint("(event_id IS NULL) <> (unit_id IS NULL)", name="target"),
        options(),
    )
    event_id: Mapped[int | None] = mapped_column(BigInteger)
    unit_id: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)


class Detector(Identity, db.Model):
    __tablename__ = "detectors"
    __table_args__ = (UniqueConstraint("detector_key"), options())
    detector_key: Mapped[str] = mapped_column(String(100), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)


class DetectorVersion(Identity, db.Model):
    __tablename__ = "detector_versions"
    __table_args__ = (
        UniqueConstraint("detector_id", "id"),
        UniqueConstraint("detector_id", "version"),
        options(),
    )
    detector_id: Mapped[int] = mapped_column(ForeignKey("detectors.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    feature_schema: Mapped[dict | None] = mapped_column(JSON)
    score_direction: Mapped[str | None] = mapped_column(String(32))


class DetectorRun(Scoped, db.Model):
    __tablename__ = "detector_runs"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "run_key"),
        ForeignKeyConstraint(
            ["detector_id", "version_id"],
            ["detector_versions.detector_id", "detector_versions.id"],
            name="fk_run_version",
        ),
        CheckConstraint("state IN ('running','completed','failed')", name="state"),
        options(),
    )
    detector_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    run_key: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    input_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evaluated_units: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)


class AnomalyOutput(Scoped, db.Model):
    __tablename__ = "anomaly_outputs"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id", "run_id"),
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "run_id", "unit_id", "signal_key"),
        scoped_fk("run_id", "detector_runs", "fk_anomaly_run_scope"),
        scoped_fk("unit_id", "detection_units", "fk_anomaly_unit_scope"),
        CheckConstraint(
            "priority IS NULL OR priority IN ('Low','Medium','High','Critical')",
            name="priority",
        ),
        Index("ix_anomalies_dataset_anchor_id", "dataset_id", "anchor_time", "id"),
        Index("ix_anomalies_dataset_run_id", "dataset_id", "run_id", "id"),  # run-scoped keyset paging
        options(),
    )
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signal_key: Mapped[str] = mapped_column(String(64), nullable=False, default="primary")
    anchor_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    priority: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[float | None] = mapped_column(DOUBLE(asdecimal=False))
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    @validates("score")
    def finite_score(self, key, value):
        if value is not None and not math.isfinite(value):
            raise ValueError("Native detection score must be finite, not a probability.")
        return value


class ProcessingJob(Scoped, db.Model):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("dataset_id", "id"),
        UniqueConstraint("dataset_id", "job_key"),
        CheckConstraint("kind IN ('ingestion','parsing','analysis')", name="kind"),
        CheckConstraint("state IN ('queued','running','completed','failed')", name="state"),
        Index("ix_processing_jobs_kind_state_id", "kind", "state", "id"),
        Index("ix_processing_jobs_upload_id", "upload_id"),
        options(),
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    processed_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    configuration: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    job_key: Mapped[str | None] = mapped_column(String(100))
    # Generated by MySQL from configuration.upload_id (migration 0005); never written by the app.
    upload_id: Mapped[str | None] = mapped_column(
        String(32),
        Computed("json_unquote(json_extract(`configuration`,_utf8mb4'$.upload_id'))", persisted=False),
    )


class CoverageInterval(Scoped, db.Model):
    __tablename__ = "coverage_intervals"
    __table_args__ = (
        scoped_fk("run_id", "detector_runs", "fk_coverage_run_scope"),
        CheckConstraint("end_time > start_time", name="bounds"),
        CheckConstraint("layer IN ('ingestion','parsing','analysis')", name="layer"),
        CheckConstraint(
            "state IN ('complete','partial','unknown','failed','not_processed')",
            name="state",
        ),
        CheckConstraint(
            "(layer = 'analysis' AND run_id IS NOT NULL) OR (layer <> 'analysis' AND run_id IS NULL)",
            name="run_layer",
        ),
        CheckConstraint("state <> 'complete' OR evidence_reference IS NOT NULL", name="proof"),
        options(),
    )
    run_id: Mapped[int | None] = mapped_column(BigInteger)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(200))
