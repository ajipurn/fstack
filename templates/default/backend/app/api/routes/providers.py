from fastapi import APIRouter

from app.api.deps import DB, Actor, DatabaseUrl
from app.db.session import transaction
from app.schemas.models import ProviderProbe, ProviderUpdate, ProviderWrite
from app.services import providers

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
def list_providers(db: DB, _: Actor):
    return providers.list_providers(db)


@router.post("", status_code=201)
def create_provider(body: ProviderWrite, db: DB, actor: Actor):
    return providers.create(db, actor, body)


@router.put("/{provider_id}")
def update_provider(provider_id: str, body: ProviderUpdate, db: DB, actor: Actor):
    return providers.update(db, actor, provider_id, body)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, db: DB, actor: Actor):
    providers.delete(db, actor, provider_id)


@router.post("/probe")
def probe(body: ProviderProbe, url: DatabaseUrl, actor: Actor):
    """Test a connection (saved or draft). The provider call runs outside a transaction."""
    with transaction(url) as db:
        spec, stored_id = providers.probe_spec(db, body)
    result = providers.run_probe(spec)
    if stored_id:
        with transaction(url) as db:
            providers.save_probe(db, actor, stored_id, result)
    return result
