"""add user permissions json field

Revision ID: 0004_user_permissions
Revises: 0003_role_permissions
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0004_user_permissions"
down_revision = "0003_role_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "permissions_json" in columns:
        return

    op.add_column(
        "users",
        sa.Column("permissions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("users", "permissions_json", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "permissions_json" not in columns:
        return

    op.drop_column("users", "permissions_json")
