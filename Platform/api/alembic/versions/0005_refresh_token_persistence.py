"""track refresh token persistence mode

Revision ID: 0005_refresh_token_persistence
Revises: 0004_user_permissions
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0005_refresh_token_persistence"
down_revision = "0004_user_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
    if "is_persistent" in columns:
        return

    op.add_column(
        "refresh_tokens",
        sa.Column("is_persistent", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("refresh_tokens", "is_persistent", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
    if "is_persistent" not in columns:
        return

    op.drop_column("refresh_tokens", "is_persistent")
