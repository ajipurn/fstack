import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


def stamp(delta: timedelta | None = None) -> str:
    """ISO-8601 UTC timestamp, sortable as text."""
    moment = datetime.now(UTC)
    if delta:
        moment += delta
    return moment.isoformat(timespec="milliseconds")


def uid() -> str:
    return str(uuid4())


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback
