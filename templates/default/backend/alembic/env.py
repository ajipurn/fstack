from alembic import context
from sqlalchemy import text

from app.db.migrations import ensure_database
from app.db.session import database_url, engine_for
from app.db.tables import metadata

config = context.config
url = config.attributes.get("database_url") or database_url()

if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
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
            context.configure(
                connection=connection,
                target_metadata=metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            if mysql:
                connection.execute(text("SELECT RELEASE_LOCK(CONCAT(DATABASE(), '-alembic'))"))
                connection.commit()
