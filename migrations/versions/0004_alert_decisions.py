"""Persist cooldown suppression so retry cannot release the old backlog."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_id",
            sa.BigInteger(),
            sa.ForeignKey("datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("anomaly_id", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.UniqueConstraint(
            "dataset_id",
            "rule_id",
            "anomaly_id",
            name="uq_alert_decisions_dataset_id_rule_id_anomaly_id",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "rule_id"],
            ["alert_rules.dataset_id", "alert_rules.id"],
            name="fk_decision_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "anomaly_id"],
            ["anomaly_outputs.dataset_id", "anomaly_outputs.id"],
            name="fk_decision_anomaly",
            ondelete="RESTRICT",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled.")
