from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import DB, Actor
from app.schemas.models import Activate, DraftSave, PromptCreate, PromptMeta, Publish
from app.services import audit, prompts

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class StartDraft(BaseModel):
    from_version_id: str | None = None


@router.get("")
def list_prompts(db: DB, _: Actor):
    return prompts.list_prompts(db)


@router.post("", status_code=201)
def create_prompt(body: PromptCreate, db: DB, actor: Actor):
    return prompts.create(db, actor, body)


@router.get("/{key}")
def get_prompt(key: str, db: DB, _: Actor):
    return prompts.get_prompt(db, key)


@router.put("/{key}")
def update_prompt(key: str, body: PromptMeta, db: DB, actor: Actor):
    return prompts.update_meta(db, actor, key, body)


@router.delete("/{key}", status_code=204)
def delete_prompt(key: str, db: DB, actor: Actor):
    prompts.delete(db, actor, key)


@router.get("/{key}/history")
def prompt_history(key: str, db: DB, _: Actor):
    return audit.recent(db, f"prompt:{key}")


@router.post("/{key}/draft", status_code=201)
def start_draft(key: str, body: StartDraft, db: DB, actor: Actor):
    return prompts.start_draft(db, actor, key, body.from_version_id)


@router.put("/{key}/draft")
def save_draft(key: str, body: DraftSave, db: DB, actor: Actor):
    return prompts.save_draft(db, actor, key, body)


@router.delete("/{key}/draft", status_code=204)
def discard_draft(key: str, db: DB, actor: Actor):
    prompts.discard_draft(db, actor, key)


@router.post("/{key}/draft/publish")
def publish(key: str, body: Publish, db: DB, actor: Actor):
    return prompts.publish(db, actor, key, body)


@router.post("/{key}/activate")
def activate(key: str, body: Activate, db: DB, actor: Actor):
    return prompts.activate(db, actor, key, body.version_id)
