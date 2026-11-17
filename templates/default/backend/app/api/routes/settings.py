from fastapi import APIRouter

from app.api.deps import DB, Actor
from app.schemas.models import SettingsUpdate
from app.services import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings(db: DB, _: Actor):
    return settings.get_all(db)


@router.put("")
def update_settings(body: SettingsUpdate, db: DB, actor: Actor):
    return settings.update(db, actor, body)
