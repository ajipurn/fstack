"""Alembic is the only migrator — no create_all, never edit an applied revision."""

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from app.core.config import BACKEND_ROOT
from app.db.session import database_url, engine_for
from app.db.tables import PREFIX, metadata

# Our own, so another app's Alembic in the same database keeps `alembic_version`.
VERSION_TABLE = f"{PREFIX}alembic_version"
# fstack's tables before they took the prefix (ai_tasks only exists before revision 0002).
UNPREFIXED = (
    "sessions",
    "login_attempts",
    "audit_events",
    "providers",
    "prompts",
    "prompt_versions",
    "model_prices",
    "llm_calls",
    "jobs",
    "worker_heartbeats",
    "ai_tasks",
)


def adopt_unprefixed(connection: sa.Connection, revisions: set[str]) -> list[str]:
    """Give a database migrated before the prefix its fstack_* names. Returns the tables
    renamed (none when there's nothing to adopt).

    Such a database keeps its revision in `alembic_version` and fstack's tables under
    their bare names. Only when that revision is one of ours, and those tables are
    there, are they renamed and `alembic_version` becomes VERSION_TABLE; another
    app's Alembic history is never touched. On MySQL their CHECK and foreign key
    names take the prefix too (see tables.py). Runs under the migration lock,
    before the revisions.
    """
    names = set(sa.inspect(connection).get_table_names())
    if VERSION_TABLE in names or "alembic_version" not in names:
        return []
    if not {"prompts", "prompt_versions", "llm_calls"} <= names:
        return []
    stamped = {
        row[0] for row in connection.execute(text("SELECT version_num FROM alembic_version"))
    }
    if not stamped or not stamped <= revisions:
        return []
    renames = [(name, PREFIX + name) for name in UNPREFIXED if name in names]
    pairs = [*renames, ("alembic_version", VERSION_TABLE)]
    quote = connection.dialect.identifier_preparer.quote
    if connection.dialect.name == "mysql":  # one atomic statement
        connection.execute(
            text("RENAME TABLE " + ", ".join(f"{quote(a)} TO {quote(b)}" for a, b in pairs))
        )
        _prefix_constraints(connection, dict(renames))
    else:  # SQLite (tests): constraint names are per table there
        for old, new in pairs:
            connection.execute(text(f"ALTER TABLE {quote(old)} RENAME TO {quote(new)}"))
    connection.commit()
    return [new for _, new in renames]


def _prefix_constraints(connection: sa.Connection, renamed: dict[str, str]) -> None:
    """MySQL can't rename a CHECK or foreign key: drop each one named the old way and add
    it back under the new name. A CHECK's expression comes from tables.py (MySQL hands
    its own back with escaped quotes); one tables.py doesn't know keeps its name."""
    quote = connection.dialect.identifier_preparer.quote
    tables = list(renamed.values())
    checks = connection.execute(
        text(
            "SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS"
            " WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'CHECK'"
            " AND TABLE_NAME IN :tables"
        ).bindparams(sa.bindparam("tables", expanding=True)),
        {"tables": tables},
    ).all()
    for table, name in checks:
        old = table.removeprefix(PREFIX)
        if not name.startswith(f"ck_{old}_"):
            continue
        new_name = f"ck_{table}_{name.removeprefix(f'ck_{old}_')}"
        known = metadata.tables.get(table)
        found = [c for c in known.constraints if c.name == new_name] if known is not None else []
        if not found or not isinstance(found[0], sa.CheckConstraint):
            continue
        expression = str(
            found[0].sqltext.compile(
                dialect=connection.dialect, compile_kwargs={"literal_binds": True}
            )
        ).replace(":", "\\:")  # text() would read a colon as a bind parameter
        connection.execute(
            text(
                f"ALTER TABLE {quote(table)} DROP CHECK {quote(name)},"
                f" ADD CONSTRAINT {quote(new_name)} CHECK ({expression})"
            )
        )

    keys = connection.execute(
        text(
            "SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.COLUMN_NAME, k.REFERENCED_TABLE_NAME,"
            " k.REFERENCED_COLUMN_NAME, r.UPDATE_RULE, r.DELETE_RULE"
            " FROM information_schema.KEY_COLUMN_USAGE k"
            " JOIN information_schema.REFERENTIAL_CONSTRAINTS r"
            " ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA"
            " AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME"
            " WHERE k.TABLE_SCHEMA = DATABASE() AND k.TABLE_NAME IN :tables"
            " ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION"
        ).bindparams(sa.bindparam("tables", expanding=True)),
        {"tables": tables},
    ).all()
    foreign: dict[tuple[str, str], list] = {}
    for row in keys:
        foreign.setdefault((row[0], row[1]), []).append(row)
    for (table, name), rows in foreign.items():
        columns, target = [r[2] for r in rows], rows[0][3]
        old, old_target = table.removeprefix(PREFIX), target.removeprefix(PREFIX)
        if name != f"fk_{old}_{columns[0]}_{old_target}":
            continue
        rules = "".join(
            f" ON {event} {rule}"
            for event, rule in (("UPDATE", rows[0][5]), ("DELETE", rows[0][6]))
            if rule not in ("NO ACTION", "RESTRICT")
        )
        connection.execute(text(f"ALTER TABLE {quote(table)} DROP FOREIGN KEY {quote(name)}"))
        connection.execute(
            text(
                f"ALTER TABLE {quote(table)} ADD CONSTRAINT"
                f" {quote(f'fk_{table}_{columns[0]}_{target}')} FOREIGN KEY"
                f" ({', '.join(quote(c) for c in columns)}) REFERENCES {quote(target)}"
                f" ({', '.join(quote(r[4]) for r in rows)}){rules}"
            )
        )


def ensure_database(url: str | None = None) -> str | None:
    """Create the MySQL database when the server doesn't have it yet.

    A shared dev server (Apple container's one `mysql`, Homebrew…) hosts every
    project, so nothing else creates it. Returns the name it created, or None.
    """
    target = make_url(database_url(url))
    if target.get_backend_name() != "mysql" or not target.database:
        return None
    # URL.set(database=None) means "unchanged"; _replace really drops it.
    server = create_engine(
        target._replace(database=None), poolclass=NullPool, connect_args={"connect_timeout": 10}
    )
    try:
        with server.connect() as connection:
            found = connection.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"),
                {"name": target.database},
            ).first()
            if found:
                return None
            quoted = target.database.replace("`", "``")
            connection.execute(
                text(f"CREATE DATABASE `{quoted}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
            )
            connection.commit()
    finally:
        server.dispose()
    return target.database


def alembic_config(url: str | None = None) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["database_url"] = database_url(url)
    return config


def migrate(url: str | None = None) -> None:
    command.upgrade(alembic_config(url), "head")


def check_schema(url: str | None = None) -> None:
    config = alembic_config(url)
    heads = set(ScriptDirectory.from_config(config).get_heads())
    with engine_for(database_url(url)).connect() as connection:
        context = MigrationContext.configure(connection, opts={"version_table": VERSION_TABLE})
        current = set(context.get_current_heads())
    if current != heads:
        raise RuntimeError("Database migrations are pending. Run `uv run tasks.py migrate`.")
