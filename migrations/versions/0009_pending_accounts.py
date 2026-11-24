"""Self-registration waits for an administrator: pending accounts cannot sign in until approved."""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts are approved; the server default only fills them in and is then removed.
    op.add_column("users", sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.alter_column(
        "users", "pending", server_default=None, existing_type=sa.Boolean(), existing_nullable=False
    )


def downgrade():
    op.drop_column("users", "pending")
