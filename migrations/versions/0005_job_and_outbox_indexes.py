"""Index worker polling, upload job lookup and the notification outbox (audit M12/M13).

- processing_jobs.upload_id: virtual generated column from configuration.upload_id, indexed, so
  the upload status/retry endpoints no longer scan (and with FOR UPDATE, lock) every job row.
- ix_processing_jobs_kind_state_id: the analysis/ingestion workers poll kind+state ORDER BY id.
- notification_outbox: (state, next_attempt, id) for the dispatcher, and a CHECK on state that
  includes the new 'sending' claim state.
- anomaly_outputs (dataset_id, run_id, id) for run-scoped keyset paging; CHECK on
  alert_decisions.outcome ('alerted', 'cooldown' are the only values ever written).
Online-friendly on MySQL 8: the virtual column adds metadata only; indexes are built in place.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPLOAD_ID = "json_unquote(json_extract(`configuration`,_utf8mb4'$.upload_id'))"


def upgrade():
    op.add_column(
        "processing_jobs",
        sa.Column("upload_id", sa.String(32), sa.Computed(UPLOAD_ID, persisted=False), nullable=True),
    )
    op.create_index("ix_processing_jobs_upload_id", "processing_jobs", ["upload_id"], unique=False)
    op.create_index("ix_processing_jobs_kind_state_id", "processing_jobs", ["kind", "state", "id"], unique=False)
    op.create_index(
        "ix_notification_outbox_state_next_attempt_id",
        "notification_outbox",
        ["state", "next_attempt", "id"],
        unique=False,
    )
    op.create_check_constraint(
        "state", "notification_outbox", "state IN ('pending','retry','sending','sent','failed')"
    )
    op.create_index("ix_anomalies_dataset_run_id", "anomaly_outputs", ["dataset_id", "run_id", "id"], unique=False)
    op.create_check_constraint("outcome", "alert_decisions", "outcome IN ('alerted','cooldown')")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled.")
