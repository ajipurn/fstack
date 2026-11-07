"""Synchronous SQLAlchemy Core with plain SQL.

Services write SQL with `?` placeholders; `Connection.execute` turns them into
named binds. MySQL (pymysql) in every real environment, SQLite only for tests
and throwaway local runs.
"""

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError  # noqa: F401  (re-exported for services)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache(maxsize=8)
def engine_for(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            connect_args={"timeout": 10, "check_same_thread": False},
            poolclass=NullPool,
            hide_parameters=True,
        )

        @event.listens_for(engine, "connect")
        def _sqlite(dbapi: Any, _: Any) -> None:
            dbapi.execute("PRAGMA foreign_keys=ON")
            dbapi.execute("PRAGMA journal_mode=WAL")

        return engine
    if url.drivername != "mysql+pymysql":
        raise ValueError("Use mysql+pymysql:// for MySQL, or sqlite:/// for tests.")
    return create_engine(
        url.update_query_dict({"charset": "utf8mb4"}),
        pool_pre_ping=True,
        pool_recycle=1800,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
        isolation_level="READ COMMITTED",
    )


class Row(dict):
    """Mapping row that also supports row[0]."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.rowcount: int = result.rowcount

    def fetchone(self) -> Row | None:
        if not self._result.returns_rows:
            return None
        row = self._result.mappings().fetchone()
        return Row(row) if row is not None else None

    def fetchall(self) -> list[Row]:
        if not self._result.returns_rows:
            return []
        return [Row(row) for row in self._result.mappings().fetchall()]

    def scalar(self) -> Any:
        row = self.fetchone()
        return None if row is None else row[0]


_TOKENS = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\?|:")


def statement(sql: str, values: Sequence[Any] = ()) -> tuple[Any, dict[str, Any]]:
    """`?` → `:p0, :p1…`; literal colons are escaped so text() leaves them alone."""
    names: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "?":
            names.append(f"p{len(names)}")
            return f":{names[-1]}"
        if token == ":":
            return r"\:"
        return token.replace(":", r"\:")

    sql = _TOKENS.sub(replace, sql)
    if len(names) != len(values):
        raise ValueError(f"SQL expects {len(names)} values, got {len(values)}.")
    return text(sql), dict(zip(names, values, strict=True))


class Connection:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @property
    def dialect(self) -> str:
        return self.connection.dialect.name

    def execute(self, sql: str, values: Sequence[Any] = ()) -> Result:
        clause, params = statement(sql, values)
        return Result(self.connection.execute(clause, params))

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        if not rows:
            return
        clause, _ = statement(sql, rows[0])
        params = [statement(sql, row)[1] for row in rows]
        self.connection.execute(clause, params)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()


def database_url(value: str | None = None) -> str:
    return value or get_settings().database_url


@contextmanager
def transaction(value: str | None = None, *, write: bool = True) -> Iterator[Connection]:
    """One unit of work. Commits on success, rolls back on any exception.

    `write=False` is a hint for SQLite (deferred BEGIN, so readers never queue
    behind a writer); MySQL behaves the same either way.
    """
    db = Connection(engine_for(database_url(value)).connect())
    try:
        if db.dialect == "sqlite":
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def for_update(db: Connection) -> str:
    """Row-lock suffix for claim queries; SQLite serialises writers anyway."""
    return " FOR UPDATE SKIP LOCKED" if db.dialect == "mysql" else ""
