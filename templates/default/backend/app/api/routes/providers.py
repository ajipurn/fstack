import logging

from fastapi import APIRouter

from app.api.deps import DB, Actor, DatabaseUrl
from app.core.exceptions import AppError
from app.db.session import transaction
from app.schemas.models import ProviderProbe, ProviderUpdate, ProviderWrite
from app.services import pricing, providers

router = APIRouter(prefix="/api/providers", tags=["providers"])
log = logging.getLogger("prices")


def load_prices(url: str) -> None:
    """Bring in models.dev prices for catalogs now in use that aren't loaded yet. Runs
    after the provider is committed, so the download holds no transaction and a failure
    leaves the provider saved (Models → Sync from models.dev retries)."""
    with transaction(url, write=False) as db:
        missing = pricing.missing_catalogs(db)
    if not missing:
        return
    try:
        data = pricing.fetch_catalog()
        with transaction(url) as db:
            pricing.sync_catalog(db, data, only=missing)
    except AppError as exc:
        log.warning("prices for %s not loaded: %s", ", ".join(sorted(missing)), exc.detail)


@router.get("")
def list_providers(db: DB, _: Actor):
    return providers.list_providers(db)


@router.post("", status_code=201)
def create_provider(body: ProviderWrite, url: DatabaseUrl, actor: Actor):
    with transaction(url) as db:
        created = providers.create(db, actor, body)
    load_prices(url)
    return created


@router.put("/{provider_id}")
def update_provider(provider_id: str, body: ProviderUpdate, url: DatabaseUrl, actor: Actor):
    with transaction(url) as db:
        updated = providers.update(db, actor, provider_id, body)
    load_prices(url)
    return updated


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
