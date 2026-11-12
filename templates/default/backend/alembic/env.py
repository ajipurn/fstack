import logging

from alembic import context
from sqlalchemy import text

from app.db.migrations import VERSION_TABLE, adopt_unprefixed, ensure_database
from app.db.session import database_url, engine_for
from app.db.tables import PREFIX, metadata

config = context.config
url = config.attributes.get("database_url") or database_url()
log = logging.getLogger("alembic.env")


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Autogenerate only sees this backend's tables: other apps' tables in the same
    database are never dropped or altered."""
    return type_ != "table" or bool(name and (name.startswith(PREFIX) or name in metadata.tables))


options = {
    "target_metadata": metadata,
    "version_table": VERSION_TABLE,
    "include_name": include_name,
}

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, **options)
    with context.begin_transaction():
        context.run_migrations()
else:
    ensure_database(url)
    with engine_for(url).connect() as connection:
        mysql = connection.dialect.name == "mysql"
        if mysql:
            version = connection.dialect.server_version_info or (0,)
            if connection.dialect.is_mariadb or version < (8, 0, 16):
                raise RuntimeError("MySQL 8.0.16+ is required (generated columns, CHECK).")
            # Two deploys migrating at once would race; serialise on a named lock.
            locked = connection.execute(
                text("SELECT GET_LOCK(CONCAT(DATABASE(), '-alembic'), 30)")
            ).scalar()
            connection.commit()
            if locked != 1:
                raise RuntimeError("Another migration is running. Retry later.")
        try:
            revisions = {script.revision for script in context.script.walk_revisions()}
            adopted = adopt_unprefixed(connection, revisions)
            if adopted:
                log.warning("schema: renamed %d tables to %s*", len(adopted), PREFIX)
            context.configure(connection=connection, compare_type=True, **options)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            if mysql:
                connection.execute(text("SELECT RELEASE_LOCK(CONCAT(DATABASE(), '-alembic'))"))
                connection.commit()
