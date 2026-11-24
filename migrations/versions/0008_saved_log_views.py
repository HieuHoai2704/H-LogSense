"""Saved Log Explorer views, kept per account (at most 20 named filter sets)."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("saved_log_views", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("users", "saved_log_views")
