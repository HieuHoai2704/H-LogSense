"""Recurring jobs: the worker queues detector runs or imports the next lines of a dataset on a schedule."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_schedules",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("import_lines", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_run_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_job_id", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "task IN ('rule','isolation_forest','import')", name=op.f("ck_job_schedules_task")
        ),
        sa.CheckConstraint(
            "interval_minutes >= 5 AND interval_minutes <= 10080", name=op.f("ck_job_schedules_interval")
        ),
        sa.CheckConstraint(
            "import_lines IS NULL OR (import_lines >= 100 AND import_lines <= 100000)",
            name=op.f("ck_job_schedules_lines"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_job_schedules_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_job_schedules_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_schedules")),
        sa.UniqueConstraint("dataset_id", "name", name=op.f("uq_job_schedules_dataset_id_name")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_job_schedules_enabled_next_run_at", "job_schedules", ["enabled", "next_run_at"])


def downgrade():
    op.drop_index("ix_job_schedules_enabled_next_run_at", table_name="job_schedules")
    op.drop_table("job_schedules")
