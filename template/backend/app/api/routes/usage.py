from fastapi import APIRouter, Query

from app.api.deps import DB, Actor
from app.core.exceptions import NotFound
from app.services import audit, calls

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/summary")
def summary(db: DB, _: Actor, days: int = Query(default=30, ge=1, le=365)):
    return calls.summary(db, days)


@router.get("/calls")
def recent_calls(
    db: DB,
    _: Actor,
    limit: int = Query(default=50, ge=1, le=200),
    prompt: str = "",
    status: str = "",
    before: str = "",
):
    return calls.recent(db, limit=limit, prompt_key=prompt, status=status, before=before)


@router.delete("/calls")
def clear_calls(db: DB, actor: Actor):
    """Wipe usage history. Prompts, providers and prices stay."""
    deleted = calls.clear(db)
    audit.record(db, actor, "usage", "usage.cleared", {"calls": deleted})
    return {"deleted": deleted}


@router.get("/calls/{call_id}")
def call_detail(call_id: str, db: DB, _: Actor):
    item = calls.detail(db, call_id)
    if not item:
        raise NotFound("Call not found.")
    return item
