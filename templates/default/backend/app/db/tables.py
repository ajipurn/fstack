"""Table definitions (SQLAlchemy Core). Alembic owns the schema; this module is
the typed reference services and tests use. Conventions:

- ids are String(80) uuid4 text; timestamps are ISO-8601 String(40) via stamp();
  lease/heartbeat times are epoch seconds (Double)
- JSON lives in LONGTEXT (`large_text()`), booleans are Integer 0/1
- every MySQL table: InnoDB, utf8mb4, utf8mb4_bin
- optimistic locking with an integer `revision`
- table names start with `fstack_` (new ones too), so the schema can share a database
  with other apps; Alembic only sees `fstack_*` tables and keeps its revision in
  `fstack_alembic_version`. CHECK and foreign key names, which MySQL scopes to the
  whole database, carry the prefix too; index names are per table and keep the bare
  name (`ix_jobs_status`), as they were before tables had the prefix.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

PREFIX = "fstack_"


def _bare_table(constraint: sa.Constraint, table: sa.Table) -> str:
    return table.name.removeprefix(PREFIX)


metadata = sa.MetaData(
    naming_convention={
        "bare_table": _bare_table,
        "ix": "ix_%(bare_table)s_%(column_0_name)s",
        "uq": "uq_%(bare_table)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(bare_table)s",
    }
)
MYSQL = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}


def large_text() -> sa.types.TypeEngine:
    return sa.Text().with_variant(LONGTEXT(), "mysql")


def ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.String(40), nullable=nullable)


sessions = sa.Table(
    "fstack_sessions",
    metadata,
    sa.Column("token_hash", sa.String(64), primary_key=True),
    # Fingerprint of the access key that opened it: a new key ends old sessions.
    sa.Column("key_id", sa.String(16), nullable=False),
    sa.Column("csrf_token", sa.String(80), nullable=False),
    sa.Column("expires_at", sa.Double(), nullable=False),
    ts("created_at"),
    **MYSQL,
)

login_attempts = sa.Table(
    "fstack_login_attempts",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("ip", sa.String(45), nullable=False),
    sa.Column("attempted_at", sa.Double(), nullable=False),
    sa.Index("ix_login_attempts_ip", "ip", "attempted_at"),
    **MYSQL,
)

audit_events = sa.Table(
    "fstack_audit_events",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("actor", sa.String(80), nullable=True),  # dashboard | api | NULL (seed)
    sa.Column("entity_id", sa.String(160), nullable=False),
    sa.Column("action", sa.String(80), nullable=False),
    sa.Column("detail", large_text(), nullable=False),
    ts("created_at"),
    sa.Index("ix_audit_events_entity_id", "entity_id", "created_at"),
    **MYSQL,
)

# ── LLM: providers, prompts ───────────────────────────────────────────────────

providers = sa.Table(
    "fstack_providers",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("name", sa.String(160), nullable=False, unique=True),
    # openai | anthropic | bedrock | google. "openai" also covers every
    # OpenAI-compatible endpoint (OpenRouter, Groq, vLLM, Ollama, Bedrock Mantle…).
    sa.Column("kind", sa.String(40), nullable=False),
    sa.Column("protocol", sa.String(40), nullable=False, server_default="chat"),
    sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
    sa.Column("region", sa.String(60), nullable=False, server_default=""),
    # models.dev provider id used for price lookup (openai, anthropic, amazon-bedrock…)
    sa.Column("catalog_id", sa.String(80), nullable=False, server_default=""),
    sa.Column("models", large_text(), nullable=False),  # JSON list[str]
    sa.Column("encrypted_secret", large_text(), nullable=False),
    sa.Column("secret_hint", sa.String(40), nullable=False, server_default=""),
    sa.Column("enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ts("last_tested_at", nullable=True),
    sa.Column("last_test_ok", sa.Integer(), nullable=True),
    sa.Column("last_test_ms", sa.Integer(), nullable=True),
    sa.Column("last_test_message", sa.String(500), nullable=True),
    ts("created_at"),
    ts("updated_at"),
    sa.CheckConstraint("kind IN ('openai','anthropic','bedrock','google')", name="valid_kind"),
    sa.CheckConstraint("protocol IN ('chat','responses')", name="valid_protocol"),
    **MYSQL,
)

prompts = sa.Table(
    "fstack_prompts",
    metadata,
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("description", sa.String(500), nullable=False, server_default=""),
    # The version runs use by default. Rollback = point at an older version.
    sa.Column("active_version_id", sa.String(80), nullable=True),
    sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ts("created_at"),
    ts("updated_at"),
    **MYSQL,
)

prompt_versions = sa.Table(
    "fstack_prompt_versions",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("prompt_key", sa.String(80), sa.ForeignKey("fstack_prompts.key"), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),  # draft | published | retired
    sa.Column("system", large_text(), nullable=False),
    sa.Column("user_template", large_text(), nullable=False),
    sa.Column("variables", large_text(), nullable=False),  # JSON list[str]
    sa.Column("note", sa.String(500), nullable=False, server_default=""),
    sa.Column("source", sa.String(20), nullable=False, server_default="ui"),  # ui | file
    sa.Column("digest", sa.String(64), nullable=False),
    sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("created_by", sa.String(80), nullable=True),
    ts("created_at"),
    ts("published_at", nullable=True),
    # MySQL has no partial unique index: a generated column that is only
    # non-NULL for drafts makes "one draft per prompt" a unique constraint.
    sa.Column(
        "draft_key",
        sa.String(80),
        sa.Computed("CASE WHEN status = 'draft' THEN prompt_key ELSE NULL END"),
        nullable=True,
    ),
    sa.UniqueConstraint("prompt_key", "version"),
    sa.UniqueConstraint("draft_key"),
    sa.CheckConstraint("status IN ('draft','published','retired')", name="valid_status"),
    **MYSQL,
)


# ── Observability ────────────────────────────────────────────────────────────

model_prices = sa.Table(
    "fstack_model_prices",
    metadata,
    sa.Column("catalog_id", sa.String(80), primary_key=True),
    sa.Column("model_id", sa.String(200), primary_key=True),
    sa.Column("name", sa.String(200), nullable=False, server_default=""),
    # USD per 1M tokens, as published by models.dev
    sa.Column("input", sa.Double(), nullable=True),
    sa.Column("output", sa.Double(), nullable=True),
    sa.Column("cache_read", sa.Double(), nullable=True),
    sa.Column("cache_write", sa.Double(), nullable=True),
    sa.Column("tiers", large_text(), nullable=True),  # JSON, context-size price tiers
    sa.Column("context_limit", sa.Integer(), nullable=True),
    sa.Column("output_limit", sa.Integer(), nullable=True),
    sa.Column("reasoning", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("source", sa.String(20), nullable=False, server_default="models.dev"),
    ts("updated_at"),
    sa.Index("ix_model_prices_model_id", "model_id"),
    **MYSQL,
)

llm_calls = sa.Table(
    "fstack_llm_calls",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("provider_id", sa.String(80), nullable=True),
    sa.Column("provider_name", sa.String(160), nullable=False, server_default=""),
    sa.Column("provider_kind", sa.String(40), nullable=False),
    sa.Column("model", sa.String(200), nullable=False),
    sa.Column("prompt_key", sa.String(80), nullable=False),
    sa.Column("prompt_version_id", sa.String(80), nullable=True),
    sa.Column("prompt_version", sa.Integer(), nullable=True),
    sa.Column("prompt_digest", sa.String(64), nullable=True),
    sa.Column("status", sa.String(20), nullable=False),  # ok | error
    sa.Column("error", sa.String(1000), nullable=True),
    sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    # NULL = no price known for this model (shown as "unpriced", never as $0).
    sa.Column("cost_usd", sa.Double(), nullable=True),
    sa.Column("pricing", large_text(), nullable=True),  # rate snapshot used for cost_usd
    sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("source", sa.String(20), nullable=False, server_default="api"),  # api|job|dashboard
    sa.Column("job_id", sa.String(80), nullable=True),
    sa.Column("user_id", sa.String(80), nullable=True),
    sa.Column("request", large_text(), nullable=True),  # only with APP_LOG_LLM_PAYLOADS
    sa.Column("response", large_text(), nullable=True),
    ts("created_at"),
    sa.Index("ix_llm_calls_created_at", "created_at"),
    sa.Index("ix_llm_calls_prompt_key", "prompt_key", "created_at"),
    sa.Index("ix_llm_calls_model", "model", "created_at"),
    sa.CheckConstraint("status IN ('ok','error')", name="valid_status"),
    **MYSQL,
)

# ── Background jobs (MySQL-leased, no blind replay) ──────────────────────────

jobs = sa.Table(
    "fstack_jobs",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(80), nullable=False),
    sa.Column("payload", large_text(), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("result", large_text(), nullable=True),
    sa.Column("error", sa.String(1000), nullable=True),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("lease_token", sa.String(80), nullable=True),
    sa.Column("lease_until", sa.Double(), nullable=True),
    sa.Column("created_by", sa.String(80), nullable=True),
    ts("created_at"),
    ts("started_at", nullable=True),
    ts("finished_at", nullable=True),
    sa.Index("ix_jobs_status", "status", "created_at"),
    sa.Index("ix_jobs_lease", "status", "lease_until"),
    sa.CheckConstraint(
        "status IN ('queued','running','succeeded','failed','interrupted','cancelled')",
        name="valid_status",
    ),
    **MYSQL,
)

worker_heartbeats = sa.Table(
    "fstack_worker_heartbeats",
    metadata,
    sa.Column("id", sa.String(80), primary_key=True),
    sa.Column("host", sa.String(255), nullable=False),
    sa.Column("last_seen", sa.Double(), nullable=False),
    ts("started_at"),
    **MYSQL,
)
