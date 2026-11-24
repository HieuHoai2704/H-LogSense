"""Authentication, persisted window predictions, jobs and incident domain."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("detection_units", sa.Column("host", sa.String(128), nullable=True))
    op.add_column("detection_units", sa.Column("definition", sa.JSON(), nullable=True))
    op.add_column("processing_jobs", sa.Column("configuration", sa.JSON(), nullable=True))
    op.add_column("processing_jobs", sa.Column("result", sa.JSON(), nullable=True))
    op.execute("ALTER TABLE processing_jobs DROP CHECK ck_processing_jobs_state")
    op.create_check_constraint(
        "state", "processing_jobs", "state IN ('queued','running','completed','failed')"
    )
    op.create_unique_constraint(
        "uq_anomaly_outputs_dataset_id_id_run_id",
        "anomaly_outputs",
        ["dataset_id", "id", "run_id"],
    )
    op.create_unique_constraint("uq_anomaly_outputs_dataset_id_id", "anomaly_outputs", ["dataset_id", "id"])
    # Frozen schema additions, reviewed.
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint("role IN ('viewer','analyst','manager','admin')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "alert_rules",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("detector_id", sa.BigInteger(), nullable=True),
        sa.Column("min_priority", sa.String(length=16), nullable=False),
        sa.Column("host", sa.String(length=128), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_alert_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "min_priority IN ('Low','Medium','High','Critical')",
            name=op.f("ck_alert_rules_priority"),
        ),
        sa.CheckConstraint(
            "cooldown_seconds >= 0 AND cooldown_seconds <= 86400",
            name=op.f("ck_alert_rules_cooldown"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_alert_rules_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["detector_id"],
            ["detectors.id"],
            name=op.f("fk_alert_rules_detector_id_detectors"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_rules")),
        sa.UniqueConstraint("dataset_id", "id", name=op.f("uq_alert_rules_dataset_id_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "user_datasets",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_user_datasets_dataset_id_datasets"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_datasets_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_datasets")),
        sa.UniqueConstraint("user_id", "dataset_id", name=op.f("uq_user_datasets_user_id_dataset_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "evaluation_reports",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id", "run_id"],
            ["detector_runs.dataset_id", "detector_runs.id"],
            name="fk_evaluation_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_evaluation_reports_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_reports")),
        sa.UniqueConstraint("dataset_id", "run_id", name=op.f("uq_evaluation_reports_dataset_id_run_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "detection_predictions",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("score", mysql.DOUBLE(), nullable=False),
        sa.Column("predicted", sa.Boolean(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id", "run_id"],
            ["detector_runs.dataset_id", "detector_runs.id"],
            name="fk_prediction_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "unit_id"],
            ["detection_units.dataset_id", "detection_units.id"],
            name="fk_prediction_unit",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_detection_predictions_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_predictions")),
        sa.UniqueConstraint(
            "dataset_id",
            "run_id",
            "unit_id",
            name=op.f("uq_detection_predictions_dataset_id_run_id_unit_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "alerts",
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("anomaly_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assigned_to", sa.BigInteger(), nullable=True),
        sa.Column("acknowledged_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','investigating','resolved')",
            name=op.f("ck_alerts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
            name=op.f("fk_alerts_acknowledged_by_users"),
        ),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], name=op.f("fk_alerts_assigned_to_users")),
        sa.ForeignKeyConstraint(
            ["dataset_id", "anomaly_id", "run_id"],
            [
                "anomaly_outputs.dataset_id",
                "anomaly_outputs.id",
                "anomaly_outputs.run_id",
            ],
            name="fk_alert_anomaly_run",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "rule_id"],
            ["alert_rules.dataset_id", "alert_rules.id"],
            name="fk_alert_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_alerts_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("dataset_id", "id", name=op.f("uq_alerts_dataset_id_id")),
        sa.UniqueConstraint(
            "dataset_id",
            "rule_id",
            "anomaly_id",
            name=op.f("uq_alerts_dataset_id_rule_id_anomaly_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "alert_audit",
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("timestamp", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name=op.f("fk_alert_audit_actor_id_users")),
        sa.ForeignKeyConstraint(
            ["dataset_id", "alert_id"],
            ["alerts.dataset_id", "alerts.id"],
            name="fk_audit_alert",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_alert_audit_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_audit")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "notification_outbox",
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 3",
            name=op.f("ck_notification_outbox_attempts"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "alert_id"],
            ["alerts.dataset_id", "alerts.id"],
            name="fk_notification_alert",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_notification_outbox_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
        sa.UniqueConstraint(
            "dataset_id",
            "alert_id",
            name=op.f("uq_notification_outbox_dataset_id_alert_id"),
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use a reviewed forward migration.")
