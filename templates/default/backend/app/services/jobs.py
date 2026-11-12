"""Background jobs on MySQL. A job is leased by one worker and fenced by a
lease token; a lost lease marks it `interrupted` — never silently replayed,
because the provider may already have billed the request."""

import time
from typing import Any

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.utils import dumps, loads, stamp, uid
from app.db.session import Connection, for_update
from app.workers.handlers import CHECKS, HANDLERS

LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 10
STALE_WORKER_SECONDS = 45
INTERRUPTED = (
    "The worker stopped while this job was running. The provider may have processed "
    "the request; start it again if you want to retry."
)


def public(row: dict[str, Any]) -> dict[str, Any]:
    item = {k: v for k, v in row.items() if k != "lease_token"}
    item["payload"] = loads(row["payload"], {})
    item["result"] = loads(row["result"])
    return item


def submit(
    db: Connection, actor: dict[str, Any], kind: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """A job submitted over the API: its payload is checked before it is queued, so a
    malformed one fails now instead of in the worker."""
    if kind not in HANDLERS:
        raise Unprocessable(f"Unknown job kind '{kind}'.")
    if check := CHECKS.get(kind):
        check(payload)
    return enqueue(db, kind, payload, actor["id"])


def enqueue(
    db: Connection, kind: str, payload: dict[str, Any], user_id: str | None = None
) -> dict[str, Any]:
    if kind not in HANDLERS:
        raise Unprocessable(f"Unknown job kind '{kind}'.")
    job_id = uid()
    db.execute(
        "INSERT INTO fstack_jobs (id, kind, payload, status, attempts, created_by, created_at)"
        " VALUES (?,?,?,'queued',0,?,?)",
        (job_id, kind, dumps(payload), user_id, stamp()),
    )
    return get(db, job_id)


def get(db: Connection, job_id: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM fstack_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise NotFound("Job not found.")
    return public(dict(row))


def recent(db: Connection, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT * FROM fstack_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [public(dict(r)) for r in rows]


def cancel(db: Connection, job_id: str) -> dict[str, Any]:
    """Queued: it never runs. Running: dropping the lease makes the worker's next
    heartbeat fail, so the run starts no new request or retry and its result is
    discarded (a request already sent finishes — it may be billed)."""
    changed = db.execute(
        "UPDATE fstack_jobs SET status='cancelled', error='Cancelled.', finished_at=?,"
        " lease_token=NULL, lease_until=NULL WHERE id=? AND status IN ('queued','running')",
        (stamp(), job_id),
    ).rowcount
    if not changed:
        get(db, job_id)
        raise Conflict("Only queued or running jobs can be cancelled.")
    return get(db, job_id)


def retry(db: Connection, actor: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Run a finished-without-success job again, as a new job with the same payload."""
    job = get(db, job_id)
    if job["status"] not in ("failed", "interrupted", "cancelled"):
        raise Conflict("Only failed, interrupted or cancelled jobs can be retried.")
    return submit(db, actor, job["kind"], job["payload"])


def expire_leases(db: Connection) -> int:
    return db.execute(
        "UPDATE fstack_jobs SET status='interrupted', error=?, finished_at=?, lease_token=NULL,"
        " lease_until=NULL WHERE status='running' AND lease_until <= ?",
        (INTERRUPTED, stamp(), time.time()),
    ).rowcount


def claim(db: Connection) -> tuple[dict[str, Any], str] | None:
    row = db.execute(
        "SELECT * FROM fstack_jobs WHERE status='queued' ORDER BY created_at, id LIMIT 1"
        + for_update(db)
    ).fetchone()
    if not row:
        return None
    token = uid()
    claimed = db.execute(
        "UPDATE fstack_jobs SET status='running', lease_token=?, lease_until=?,"
        " attempts=attempts+1, started_at=? WHERE id=? AND status='queued'",
        (token, time.time() + LEASE_SECONDS, stamp(), row["id"]),
    ).rowcount
    return (dict(row), token) if claimed else None


def heartbeat(db: Connection, job_id: str, token: str) -> bool:
    return bool(
        db.execute(
            "UPDATE fstack_jobs SET lease_until=? WHERE id=? AND status='running' AND lease_token=?"
            " AND lease_until > ?",
            (time.time() + LEASE_SECONDS, job_id, token, time.time()),
        ).rowcount
    )


def finish(
    db: Connection, job_id: str, token: str, *, result: Any = None, error: str | None = None
) -> bool:
    """Fenced write: only the lease holder can record the outcome."""
    return bool(
        db.execute(
            "UPDATE fstack_jobs SET status=?, result=?, error=?, finished_at=?, lease_token=NULL,"
            " lease_until=NULL WHERE id=? AND status='running' AND lease_token=?",
            (
                "failed" if error else "succeeded",
                None if result is None else dumps(result),
                (error or "")[:1000] or None,
                stamp(),
                job_id,
                token,
            ),
        ).rowcount
    )


def worker_status(db: Connection) -> dict[str, Any]:
    cutoff = time.time() - STALE_WORKER_SECONDS
    live = db.execute(
        "SELECT COUNT(*) FROM fstack_worker_heartbeats WHERE last_seen > ?", (cutoff,)
    ).scalar()
    queued = db.execute("SELECT COUNT(*) FROM fstack_jobs WHERE status='queued'").scalar()
    running = db.execute("SELECT COUNT(*) FROM fstack_jobs WHERE status='running'").scalar()
    return {
        "online": bool(live),
        "workers": int(live or 0),
        "queued": int(queued or 0),
        "running": int(running or 0),
    }
