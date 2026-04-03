"""add role permissions json field

Revision ID: 0003_role_permissions
Revises: 0002_password_reset_tokens
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "0003_role_permissions"
down_revision = "0002_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("roles")}
    if "permissions_json" in columns:
        return

    op.add_column(
        "roles",
        sa.Column("permissions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("roles", "permissions_json", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("roles")}
    if "permissions_json" not in columns:
        return

    op.drop_column("roles", "permissions_json")
