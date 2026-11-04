"""Idempotent analysis-job submission."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "processing_jobs", sa.Column("job_key", sa.String(100), nullable=True)
    )
    op.create_unique_constraint(
        "uq_processing_jobs_dataset_id_job_key",
        "processing_jobs",
        ["dataset_id", "job_key"],
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled.")
