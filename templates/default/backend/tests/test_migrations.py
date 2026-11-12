from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from app.db.migrations import UNPREFIXED, VERSION_TABLE, check_schema, migrate
from app.db.session import engine_for, transaction
from app.db.tables import PREFIX, metadata


def tables(url: str) -> set[str]:
    with engine_for(url).connect() as connection:
        return set(sa.inspect(connection).get_table_names())


def schema_diff(url: str) -> list:
    with engine_for(url).connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "version_table": VERSION_TABLE,
                "compare_type": True,
                "include_name": lambda name, type_, _: type_ != "table" or name.startswith(PREFIX),
            },
        )
        return compare_metadata(context, metadata)


def test_every_table_is_prefixed_and_matches_tables_py(database: str) -> None:
    assert all(name.startswith(PREFIX) for name in tables(database))
    assert set(metadata.tables) | {VERSION_TABLE} == tables(database)
    assert schema_diff(database) == []


def test_other_apps_tables_and_alembic_history_are_left_alone(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'shared.db'}"
    with engine_for(url).begin() as connection:
        connection.execute(sa.text("CREATE TABLE jobs (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(sa.text("INSERT INTO alembic_version VALUES ('their_rev')"))
    migrate(url)
    check_schema(url)
    assert {"jobs", "alembic_version", "fstack_jobs", VERSION_TABLE} <= tables(url)
    with engine_for(url).connect() as connection:
        version = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    assert version == "their_rev"
    assert schema_diff(url) == []  # autogenerate never proposes dropping their tables


def test_a_database_from_before_the_prefix_is_renamed(database: str) -> None:
    with transaction(database) as db:
        prompts = db.execute("SELECT COUNT(*) FROM fstack_prompts").scalar()
    assert prompts
    # Put it back the way 0.3.0 left it: bare table names, revision in alembic_version.
    with engine_for(database).begin() as connection:
        for name in UNPREFIXED[:-1]:
            connection.execute(sa.text(f"ALTER TABLE {PREFIX}{name} RENAME TO {name}"))
        connection.execute(sa.text(f"ALTER TABLE {VERSION_TABLE} RENAME TO alembic_version"))

    migrate(database)
    check_schema(database)
    assert tables(database) == set(metadata.tables) | {VERSION_TABLE}
    with transaction(database) as db:
        assert db.execute("SELECT COUNT(*) FROM fstack_prompts").scalar() == prompts
    assert schema_diff(database) == []
