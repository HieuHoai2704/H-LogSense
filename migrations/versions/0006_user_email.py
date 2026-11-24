"""Account e-mail for self-registration and password reset.

users.email is optional (accounts created by the operator CLI may have none) and unique when present;
MySQL unique indexes allow several NULLs.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade():
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "email")
