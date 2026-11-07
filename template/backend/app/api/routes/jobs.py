from fastapi import APIRouter

from app.api.deps import DB, Actor
from app.schemas.models import JobCreate
from app.services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(db: DB, _: Actor):
    return {"worker": jobs.worker_status(db), "jobs": jobs.recent(db)}


@router.post("", status_code=202)
def create_job(body: JobCreate, db: DB, actor: Actor):
    return jobs.submit(db, actor, body.kind, body.payload)


@router.get("/{job_id}")
def get_job(job_id: str, db: DB, _: Actor):
    return jobs.get(db, job_id)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: DB, _: Actor):
    return jobs.cancel(db, job_id)


@router.post("/{job_id}/retry", status_code=202)
def retry_job(job_id: str, db: DB, actor: Actor):
    return jobs.retry(db, actor, job_id)
