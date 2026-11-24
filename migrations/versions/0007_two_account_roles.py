"""Two account types: staff (the whole application) and admin (also manages accounts).

The former viewer, analyst and manager roles become staff; admin stays admin.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.execute("UPDATE users SET role = 'staff' WHERE role IN ('viewer', 'analyst', 'manager')")
    op.create_check_constraint(op.f("ck_users_role"), "users", "role IN ('staff','admin')")


def downgrade():
    # The finer roles cannot be recovered; staff returns as analyst (investigation without dataset admin).
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.execute("UPDATE users SET role = 'analyst' WHERE role = 'staff'")
    op.create_check_constraint(
        op.f("ck_users_role"), "users", "role IN ('viewer','analyst','manager','admin')"
    )
