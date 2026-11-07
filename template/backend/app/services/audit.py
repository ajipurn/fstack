from typing import Any

from app.core.utils import dumps, stamp, uid
from app.db.session import Connection


def record(
    db: Connection,
    actor: dict[str, Any] | None,
    entity_id: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Dotted action names: prompt.published, provider.tested, provider.updated…
    `actor` is "dashboard", "api", or None for seed/system work."""
    db.execute(
        "INSERT INTO audit_events (id, actor, entity_id, action, detail, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (uid(), (actor or {}).get("id"), entity_id, action, dumps(detail or {}), stamp()),
    )


def recent(db: Connection, entity_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT * FROM audit_events"
    values: list[Any] = []
    if entity_id:
        sql += " WHERE entity_id=?"
        values.append(entity_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    values.append(limit)
    return [dict(r) for r in db.execute(sql, values).fetchall()]
