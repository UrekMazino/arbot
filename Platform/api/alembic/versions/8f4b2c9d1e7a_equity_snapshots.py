"""Equity snapshots

Revision ID: 8f4b2c9d1e7a
Revises: 5d6b8f9c1a2e
Create Date: 2026-04-21 12:45:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f4b2c9d1e7a"
down_revision = "5d6b8f9c1a2e"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("equity_snapshots"):
        op.create_table(
            "equity_snapshots",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("run_id", sa.String(length=36), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("equity_usdt", sa.Numeric(20, 8), nullable=False),
            sa.Column("session_pnl_usdt", sa.Numeric(20, 8), nullable=True),
            sa.Column("session_pnl_pct", sa.Float(), nullable=True),
            sa.Column("current_pair", sa.String(length=120), nullable=True),
            sa.Column("regime", sa.String(length=30), nullable=True),
            sa.Column("strategy", sa.String(length=50), nullable=True),
            sa.Column("in_position", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("entry_z", sa.Float(), nullable=True),
            sa.Column("current_z", sa.Float(), nullable=True),
            sa.Column("hold_minutes", sa.Float(), nullable=True),
            sa.Column("unrealized_pnl_usdt", sa.Numeric(20, 8), nullable=True),
            sa.Column("source", sa.String(length=30), nullable=False, server_default="heartbeat"),
            sa.Column("source_event_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_event_id", name="uq_equity_snapshots_source_event_id"),
        )

    existing_indexes = {row.get("name") for row in inspector.get_indexes("equity_snapshots")}
    wanted_indexes = [
        (op.f("ix_equity_snapshots_run_id"), ["run_id"]),
        (op.f("ix_equity_snapshots_ts"), ["ts"]),
        (op.f("ix_equity_snapshots_current_pair"), ["current_pair"]),
        (op.f("ix_equity_snapshots_regime"), ["regime"]),
        (op.f("ix_equity_snapshots_strategy"), ["strategy"]),
        (op.f("ix_equity_snapshots_source"), ["source"]),
    ]
    for index_name, columns in wanted_indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "equity_snapshots", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("equity_snapshots"):
        return

    existing_indexes = {row.get("name") for row in inspector.get_indexes("equity_snapshots")}
    for index_name in [
        op.f("ix_equity_snapshots_source"),
        op.f("ix_equity_snapshots_strategy"),
        op.f("ix_equity_snapshots_regime"),
        op.f("ix_equity_snapshots_current_pair"),
        op.f("ix_equity_snapshots_ts"),
        op.f("ix_equity_snapshots_run_id"),
    ]:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="equity_snapshots")

    op.drop_table("equity_snapshots")
