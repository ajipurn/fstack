"""Workspace settings: preferences the dashboard sets for everyone (Configure → Layout).

Each key has a default here; a key with no row reads as its default, so a new setting
needs no migration. Values are JSON in `fstack_settings`.
"""

from typing import Any

from app.core.utils import dumps, loads, stamp
from app.db.session import Connection, IntegrityError
from app.schemas.models import SettingsUpdate
from app.services import audit

DEFAULTS: dict[str, Any] = {
    "nav_position": "top",  # "top": header with tabs; "side": sidebar on the left
}


def get_all(db: Connection) -> dict[str, Any]:
    rows = db.execute("SELECT `key`, value FROM fstack_settings").fetchall()
    stored = {row["key"]: loads(row["value"]) for row in rows if row["key"] in DEFAULTS}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if v is not None}}


def update(db: Connection, actor: dict[str, Any], body: SettingsUpdate) -> dict[str, Any]:
    """Save the fields `body` sets; the rest keep their values."""
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    current = get_all(db)
    for key, value in changes.items():
        if current.get(key) == value:
            continue
        _put(db, actor, key, value)
        audit.record(
            db, actor, f"setting:{key}", "setting.updated", {"from": current.get(key), "to": value}
        )
    return get_all(db)


def _put(db: Connection, actor: dict[str, Any], key: str, value: Any) -> None:
    now, by = stamp(), actor.get("id")
    sql = "UPDATE fstack_settings SET value=?, updated_at=?, updated_by=? WHERE `key`=?"
    if db.execute(sql, (dumps(value), now, by, key)).rowcount:
        return
    try:
        db.execute(
            "INSERT INTO fstack_settings (`key`, value, updated_at, updated_by) VALUES (?,?,?,?)",
            (key, dumps(value), now, by),
        )
    except IntegrityError:  # another request inserted it first: ours is the later write
        db.execute(sql, (dumps(value), now, by, key))
