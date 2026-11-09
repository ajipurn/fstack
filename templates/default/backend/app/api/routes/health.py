import time

from fastapi import APIRouter

from app.api.deps import DB
from app.core.config import get_settings
from app.services import jobs

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(db: DB):
    started = time.monotonic()
    db.execute("SELECT 1")
    return {
        "status": "ok",
        "service": get_settings().app_name,
        "environment": get_settings().environment,
        "database_ms": round((time.monotonic() - started) * 1000, 1),
        "worker": jobs.worker_status(db),
    }
