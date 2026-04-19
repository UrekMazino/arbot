"""Run pair segments

Revision ID: 5d6b8f9c1a2e
Revises: 2a6341d32e9c
Create Date: 2026-04-18 13:55:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5d6b8f9c1a2e"
down_revision = "2a6341d32e9c"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("run_pair_segments"):
        op.create_table(
            "run_pair_segments",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("run_id", sa.String(length=36), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("pair_key", sa.String(length=120), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("switch_reason", sa.String(length=80), nullable=True),
            sa.Column("start_event_id", sa.String(length=36), nullable=True),
            sa.Column("end_event_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "sequence_no", name="uq_run_pair_segments_run_sequence"),
        )

    existing_indexes = {row.get("name") for row in inspector.get_indexes("run_pair_segments")}
    wanted_indexes = [
        (op.f("ix_run_pair_segments_run_id"), ["run_id"]),
        (op.f("ix_run_pair_segments_pair_key"), ["pair_key"]),
        (op.f("ix_run_pair_segments_started_at"), ["started_at"]),
        (op.f("ix_run_pair_segments_ended_at"), ["ended_at"]),
        (op.f("ix_run_pair_segments_start_event_id"), ["start_event_id"]),
        (op.f("ix_run_pair_segments_end_event_id"), ["end_event_id"]),
    ]
    for index_name, columns in wanted_indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "run_pair_segments", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("run_pair_segments"):
        return

    existing_indexes = {row.get("name") for row in inspector.get_indexes("run_pair_segments")}
    for index_name in [
        op.f("ix_run_pair_segments_end_event_id"),
        op.f("ix_run_pair_segments_start_event_id"),
        op.f("ix_run_pair_segments_ended_at"),
        op.f("ix_run_pair_segments_started_at"),
        op.f("ix_run_pair_segments_pair_key"),
        op.f("ix_run_pair_segments_run_id"),
    ]:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="run_pair_segments")

    op.drop_table("run_pair_segments")
