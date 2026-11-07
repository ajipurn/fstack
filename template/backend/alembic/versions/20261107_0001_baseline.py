"""Baseline schema: access-key sessions, providers, prompt versions, task bindings, prices,
llm_calls observability and leased jobs.

Revision ID: 0001
Revises:
Create Date: 2026-11-07 16:04:04.265173
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_audit_events_entity_id", "audit_events", ["entity_id", "created_at"], unique=False
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("lease_token", sa.String(length=80), nullable=True),
        sa.Column("lease_until", sa.Double(), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("finished_at", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','interrupted','cancelled')",
            name=op.f("ck_jobs_valid_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_jobs_lease", "jobs", ["status", "lease_until"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status", "created_at"], unique=False)
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("task_key", sa.String(length=80), nullable=False),
        sa.Column("provider_id", sa.String(length=80), nullable=True),
        sa.Column("provider_name", sa.String(length=160), server_default="", nullable=False),
        sa.Column("provider_kind", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_key", sa.String(length=80), nullable=False),
        sa.Column("prompt_version_id", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("prompt_digest", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Double(), nullable=True),
        sa.Column("pricing", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=True),
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.String(length=20), server_default="api", nullable=False),
        sa.Column("job_id", sa.String(length=80), nullable=True),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("request", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=True),
        sa.Column("response", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint("status IN ('ok','error')", name=op.f("ck_llm_calls_valid_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"], unique=False)
    op.create_index("ix_llm_calls_model", "llm_calls", ["model", "created_at"], unique=False)
    op.create_index("ix_llm_calls_task_key", "llm_calls", ["task_key", "created_at"], unique=False)
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("attempted_at", sa.Double(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip", "attempted_at"], unique=False)
    op.create_table(
        "model_prices",
        sa.Column("catalog_id", sa.String(length=80), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), server_default="", nullable=False),
        sa.Column("input", sa.Double(), nullable=True),
        sa.Column("output", sa.Double(), nullable=True),
        sa.Column("cache_read", sa.Double(), nullable=True),
        sa.Column("cache_write", sa.Double(), nullable=True),
        sa.Column("tiers", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=True),
        sa.Column("context_limit", sa.Integer(), nullable=True),
        sa.Column("output_limit", sa.Integer(), nullable=True),
        sa.Column("reasoning", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.String(length=20), server_default="models.dev", nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("catalog_id", "model_id", name=op.f("pk_model_prices")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_model_prices_model_id", "model_prices", ["model_id"], unique=False)
    op.create_table(
        "prompts",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), server_default="", nullable=False),
        sa.Column("active_version_id", sa.String(length=80), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_prompts")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("protocol", sa.String(length=40), server_default="chat", nullable=False),
        sa.Column("base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("region", sa.String(length=60), server_default="", nullable=False),
        sa.Column("catalog_id", sa.String(length=80), server_default="", nullable=False),
        sa.Column("models", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column(
            "encrypted_secret", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False
        ),
        sa.Column("secret_hint", sa.String(length=40), server_default="", nullable=False),
        sa.Column("enabled", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_tested_at", sa.String(length=40), nullable=True),
        sa.Column("last_test_ok", sa.Integer(), nullable=True),
        sa.Column("last_test_ms", sa.Integer(), nullable=True),
        sa.Column("last_test_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "kind IN ('openai','anthropic','bedrock','google')",
            name=op.f("ck_providers_valid_kind"),
        ),
        sa.CheckConstraint(
            "protocol IN ('chat','responses')", name=op.f("ck_providers_valid_protocol")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_providers")),
        sa.UniqueConstraint("name", name=op.f("uq_providers_name")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("last_seen", sa.Double(), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_heartbeats")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "ai_tasks",
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
            ["prompt_key"], ["prompts.key"], name=op.f("fk_ai_tasks_prompt_key_prompts")
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], name=op.f("fk_ai_tasks_provider_id_providers")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_ai_tasks")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_ai_tasks_prompt_key", "ai_tasks", ["prompt_key"], unique=False)
    op.create_index("ix_ai_tasks_provider_id", "ai_tasks", ["provider_id"], unique=False)
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("prompt_key", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("system", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column(
            "user_template", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False
        ),
        sa.Column("variables", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("source", sa.String(length=20), server_default="ui", nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("published_at", sa.String(length=40), nullable=True),
        sa.Column(
            "draft_key",
            sa.String(length=80),
            sa.Computed(
                "CASE WHEN status = 'draft' THEN prompt_key ELSE NULL END",
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('draft','published','retired')",
            name=op.f("ck_prompt_versions_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["prompt_key"], ["prompts.key"], name=op.f("fk_prompt_versions_prompt_key_prompts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_versions")),
        sa.UniqueConstraint("draft_key", name=op.f("uq_prompt_versions_draft_key")),
        sa.UniqueConstraint(
            "prompt_key", "version", name=op.f("uq_prompt_versions_prompt_key_version")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("key_id", sa.String(length=16), nullable=False),
        sa.Column("csrf_token", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.Double(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sessions")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_ai_tasks_provider_id", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_prompt_key", table_name="ai_tasks")
    op.drop_table("ai_tasks")
    op.drop_table("worker_heartbeats")
    op.drop_table("providers")
    op.drop_table("prompts")
    op.drop_index("ix_model_prices_model_id", table_name="model_prices")
    op.drop_table("model_prices")
    op.drop_index("ix_login_attempts_ip", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_llm_calls_task_key", table_name="llm_calls")
    op.drop_index("ix_llm_calls_model", table_name="llm_calls")
    op.drop_index("ix_llm_calls_created_at", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_lease", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_audit_events_entity_id", table_name="audit_events")
    op.drop_table("audit_events")
