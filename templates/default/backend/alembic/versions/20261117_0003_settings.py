"""Workspace settings: preferences set from the dashboard, such as the navigation layout.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fstack_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    op.drop_table("fstack_settings")
