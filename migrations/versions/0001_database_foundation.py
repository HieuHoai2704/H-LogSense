"""Initial MySQL 8 foundation, frozen DDL independent of runtime models."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Frozen and reviewed initial DDL.
    op.create_table(
        "data_sources",
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_sources")),
        sa.UniqueConstraint("source_key", name=op.f("uq_data_sources_source_key")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "detectors",
        sa.Column("detector_key", sa.String(length=100), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detectors")),
        sa.UniqueConstraint("detector_key", name=op.f("uq_detectors_detector_key")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "datasets",
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("data_mode", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("input_revision", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "data_mode IN ('real','synthetic','unverified')",
            name=op.f("ck_datasets_mode"),
        ),
        sa.CheckConstraint(
            "state IN ('registered','importing','partial','imported','failed','archived')",
            name=op.f("ck_datasets_state"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_datasets_source_id_data_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint(
            "source_id", "dataset_key", name=op.f("uq_datasets_source_id_dataset_key")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "detector_versions",
        sa.Column("detector_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("feature_schema", sa.JSON(), nullable=True),
        sa.Column("score_direction", sa.String(length=32), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["detector_id"],
            ["detectors.id"],
            name=op.f("fk_detector_versions_detector_id_detectors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detector_versions")),
        sa.UniqueConstraint(
            "detector_id", "id", name=op.f("uq_detector_versions_detector_id_id")
        ),
        sa.UniqueConstraint(
            "detector_id",
            "version",
            name=op.f("uq_detector_versions_detector_id_version"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "detector_runs",
        sa.Column("detector_id", sa.BigInteger(), nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("run_key", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("input_revision", sa.BigInteger(), nullable=False),
        sa.Column("evaluated_units", sa.BigInteger(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "state IN ('running','completed','failed')",
            name=op.f("ck_detector_runs_state"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_detector_runs_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["detector_id", "version_id"],
            ["detector_versions.detector_id", "detector_versions.id"],
            name="fk_run_version",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detector_runs")),
        sa.UniqueConstraint(
            "dataset_id", "id", name=op.f("uq_detector_runs_dataset_id_id")
        ),
        sa.UniqueConstraint(
            "dataset_id", "run_key", name=op.f("uq_detector_runs_dataset_id_run_key")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "processing_jobs",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("processed_count", sa.BigInteger(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "kind IN ('ingestion','parsing','analysis')",
            name=op.f("ck_processing_jobs_kind"),
        ),
        sa.CheckConstraint(
            "state IN ('running','completed','failed')",
            name=op.f("ck_processing_jobs_state"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_processing_jobs_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
        sa.UniqueConstraint(
            "dataset_id", "id", name=op.f("uq_processing_jobs_dataset_id_id")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "source_artifacts",
        sa.Column("artifact_key", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_length", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("checkpoint_line", sa.BigInteger(), nullable=False),
        sa.Column("checkpoint_byte", sa.BigInteger(), nullable=False),
        sa.Column("parsed_count", sa.BigInteger(), nullable=False),
        sa.Column("malformed_count", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "byte_length >= 0 AND checkpoint_line >= 0 AND checkpoint_byte >= 0 AND checkpoint_byte <= byte_length AND parsed_count >= 0 AND malformed_count >= 0 AND parsed_count + malformed_count = checkpoint_line",
            name=op.f("ck_source_artifacts_checkpoint"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_source_artifacts_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_artifacts")),
        sa.UniqueConstraint(
            "dataset_id",
            "artifact_key",
            name=op.f("uq_source_artifacts_dataset_id_artifact_key"),
        ),
        sa.UniqueConstraint(
            "dataset_id", "id", name=op.f("uq_source_artifacts_dataset_id_id")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "coverage_intervals",
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("layer", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("start_time", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("end_time", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("evidence_reference", sa.String(length=200), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "(layer = 'analysis' AND run_id IS NOT NULL) OR (layer <> 'analysis' AND run_id IS NULL)",
            name=op.f("ck_coverage_intervals_run_layer"),
        ),
        sa.CheckConstraint(
            "layer IN ('ingestion','parsing','analysis')",
            name=op.f("ck_coverage_intervals_layer"),
        ),
        sa.CheckConstraint(
            "state <> 'complete' OR evidence_reference IS NOT NULL",
            name=op.f("ck_coverage_intervals_proof"),
        ),
        sa.CheckConstraint(
            "state IN ('complete','partial','unknown','failed','not_processed')",
            name=op.f("ck_coverage_intervals_state"),
        ),
        sa.CheckConstraint(
            "end_time > start_time", name=op.f("ck_coverage_intervals_bounds")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "run_id"],
            ["detector_runs.dataset_id", "detector_runs.id"],
            name="fk_coverage_run_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_coverage_intervals_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coverage_intervals")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "raw_log_records",
        sa.Column("artifact_id", sa.BigInteger(), nullable=False),
        sa.Column("line_number", sa.BigInteger(), nullable=False),
        sa.Column("byte_offset", sa.BigInteger(), nullable=False),
        sa.Column("raw_bytes", mysql.LONGBLOB(), nullable=False),
        sa.Column("parse_error", sa.String(length=64), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "line_number > 0 AND byte_offset >= 0",
            name=op.f("ck_raw_log_records_position"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "artifact_id"],
            ["source_artifacts.dataset_id", "source_artifacts.id"],
            name="fk_raw_artifact_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_raw_log_records_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_log_records")),
        sa.UniqueConstraint(
            "dataset_id",
            "artifact_id",
            "line_number",
            name=op.f("uq_raw_log_records_dataset_id_artifact_id_line_number"),
        ),
        sa.UniqueConstraint(
            "dataset_id", "id", name=op.f("uq_raw_log_records_dataset_id_id")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "log_events",
        sa.Column("raw_id", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("emit_index", sa.Integer(), nullable=False),
        sa.Column("timestamp", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("raw_timestamp", sa.String(length=100), nullable=False),
        sa.Column("host", sa.String(length=128), nullable=True),
        sa.Column("service", sa.String(length=128), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("message", mysql.LONGTEXT(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id", "raw_id"],
            ["raw_log_records.dataset_id", "raw_log_records.id"],
            name="fk_event_raw_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_log_events_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_log_events")),
        sa.UniqueConstraint(
            "dataset_id", "id", name=op.f("uq_log_events_dataset_id_id")
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "raw_id",
            "parser_version",
            "emit_index",
            name=op.f("uq_log_events_dataset_id_raw_id_parser_version_emit_index"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_events_dataset_time_id",
        "log_events",
        ["dataset_id", "timestamp", "id"],
        unique=False,
    )
    op.create_index(
        "ix_events_dataset_host_time",
        "log_events",
        ["dataset_id", "host", "timestamp", "id"],
        unique=False,
    )
    op.create_table(
        "detection_units",
        sa.Column("unit_key", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("start_time", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("end_time", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "(kind = 'event' AND event_id IS NOT NULL AND end_time IS NULL) OR (kind = 'window' AND event_id IS NULL AND end_time IS NOT NULL AND end_time > start_time) OR (kind IN ('block','session') AND event_id IS NULL AND (end_time IS NULL OR end_time > start_time))",
            name=op.f("ck_detection_units_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "event_id"],
            ["log_events.dataset_id", "log_events.id"],
            name="fk_unit_event_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_detection_units_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_units")),
        sa.UniqueConstraint(
            "dataset_id", "id", name=op.f("uq_detection_units_dataset_id_id")
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "unit_key",
            name=op.f("uq_detection_units_dataset_id_unit_key"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "anomaly_outputs",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("signal_key", sa.String(length=64), nullable=False),
        sa.Column("anchor_time", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=True),
        sa.Column("score", mysql.DOUBLE(asdecimal=False), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "priority IS NULL OR priority IN ('Low','Medium','High','Critical')",
            name=op.f("ck_anomaly_outputs_priority"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "run_id"],
            ["detector_runs.dataset_id", "detector_runs.id"],
            name="fk_anomaly_run_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "unit_id"],
            ["detection_units.dataset_id", "detection_units.id"],
            name="fk_anomaly_unit_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_anomaly_outputs_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anomaly_outputs")),
        sa.UniqueConstraint(
            "dataset_id",
            "run_id",
            "unit_id",
            "signal_key",
            name=op.f("uq_anomaly_outputs_dataset_id_run_id_unit_id_signal_key"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_anomalies_dataset_anchor_id",
        "anomaly_outputs",
        ["dataset_id", "anchor_time", "id"],
        unique=False,
    )
    op.create_table(
        "ground_truth_labels",
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("unit_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "(event_id IS NULL) <> (unit_id IS NULL)",
            name=op.f("ck_ground_truth_labels_target"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "event_id"],
            ["log_events.dataset_id", "log_events.id"],
            name="fk_label_event_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "unit_id"],
            ["detection_units.dataset_id", "detection_units.id"],
            name="fk_label_unit_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_ground_truth_labels_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ground_truth_labels")),
        sa.UniqueConstraint(
            "dataset_id",
            "event_id",
            "source",
            "version",
            name=op.f("uq_ground_truth_labels_dataset_id_event_id_source_version"),
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "unit_id",
            "source",
            "version",
            name=op.f("uq_ground_truth_labels_dataset_id_unit_id_source_version"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "unit_events",
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id", "event_id"],
            ["log_events.dataset_id", "log_events.id"],
            name="fk_membership_event_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "unit_id"],
            ["detection_units.dataset_id", "detection_units.id"],
            name="fk_membership_unit_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_unit_events_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_events")),
        sa.UniqueConstraint(
            "dataset_id",
            "unit_id",
            "event_id",
            name=op.f("uq_unit_events_dataset_id_unit_id_event_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )


def downgrade():
    raise RuntimeError(
        "Destructive initial downgrade is disabled; use a forward migration or restore an isolated backup."
    )
