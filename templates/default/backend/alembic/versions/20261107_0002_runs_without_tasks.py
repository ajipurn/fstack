"""Runs pick prompt, provider and model themselves: drop task bindings.

ai_tasks goes away, and llm_calls is grouped by prompt instead of task.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Its indexes back foreign keys (MySQL won't drop them alone); they go with the table.
    op.drop_table("fstack_ai_tasks")
    # Batch mode: SQLite (tests) rebuilds the table; MySQL alters it in place.
    with op.batch_alter_table("fstack_llm_calls") as batch:
        batch.drop_index("ix_llm_calls_task_key")
        batch.drop_column("task_key")
        batch.create_index("ix_llm_calls_prompt_key", ["prompt_key", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("fstack_llm_calls") as batch:
        batch.drop_index("ix_llm_calls_prompt_key")
        batch.add_column(
            sa.Column("task_key", sa.String(length=80), server_default="", nullable=False)
        )
        batch.create_index("ix_llm_calls_task_key", ["task_key", "created_at"], unique=False)
    op.create_table(
        "fstack_ai_tasks",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("prompt_key", sa.String(length=80), nullable=False),
        sa.Column("provider_id", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=200), server_default="", nullable=False),
        sa.Column("temperature", sa.Double(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), server_default=sa.text("4096"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["prompt_key"],
            ["fstack_prompts.key"],
            name=op.f("fk_fstack_ai_tasks_prompt_key_fstack_prompts"),
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["fstack_providers.id"],
            name=op.f("fk_fstack_ai_tasks_provider_id_fstack_providers"),
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_ai_tasks")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_ai_tasks_prompt_key", "fstack_ai_tasks", ["prompt_key"], unique=False)
    op.create_index("ix_ai_tasks_provider_id", "fstack_ai_tasks", ["provider_id"], unique=False)
