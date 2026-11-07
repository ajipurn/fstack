from fastapi import APIRouter

from app.api.deps import DB, Actor, DatabaseUrl
from app.db.session import transaction
from app.schemas.models import ManualPrice
from app.services import audit, pricing

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def search(db: DB, _: Actor, catalog: str = "", q: str = "", limit: int = 100):
    return {
        "summary": pricing.catalog_summary(db),
        "catalogs": pricing.list_catalogs(db),
        "models": pricing.search_models(db, catalog, q, limit),
    }


@router.post("/sync")
def sync(url: DatabaseUrl, actor: Actor):
    data = pricing.fetch_catalog()  # download outside the transaction
    with transaction(url) as db:
        result = pricing.sync_catalog(db, data)
        audit.record(db, actor, "models.dev", "prices.synced", result)
    return result


@router.put("/manual")
def manual_price(body: ManualPrice, db: DB, actor: Actor):
    pricing.set_manual_price(
        db,
        body.catalog_id,
        body.model_id,
        body.model_dump(include={"input", "output", "cache_read", "cache_write"}),
        body.name,
    )
    audit.record(db, actor, f"{body.catalog_id}/{body.model_id}", "prices.manual_set")
    return pricing.search_models(db, body.catalog_id, body.model_id, 1)
