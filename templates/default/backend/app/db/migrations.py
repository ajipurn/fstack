"""Alembic is the only migrator — no create_all, never edit an applied revision."""

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from app.core.config import BACKEND_ROOT
from app.db.session import database_url, engine_for


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
        current = set(MigrationContext.configure(connection).get_current_heads())
    if current != heads:
        raise RuntimeError("Database migrations are pending. Run `make migrate`.")
