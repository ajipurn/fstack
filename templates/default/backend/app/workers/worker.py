"""`make worker` — leased job loop. Run it as its own process/service; API
restarts don't stop it and it never replays a job whose lease was lost."""

import logging
import signal
import socket
import threading
import time
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.utils import loads, stamp, uid
from app.db.migrations import check_schema
from app.db.session import transaction
from app.llm.errors import scrub
from app.services import jobs
from app.workers.handlers import HANDLERS, JobContext

log = logging.getLogger("worker")


def process_one(database_url: str) -> bool:
    with transaction(database_url) as db:
        jobs.expire_leases(db)
        claimed = jobs.claim(db)
    if not claimed:
        return False
    job, token = claimed
    lost = threading.Event()
    done = threading.Event()

    def beat() -> None:
        while not done.wait(jobs.HEARTBEAT_SECONDS):
            try:
                with transaction(database_url) as db:
                    if not jobs.heartbeat(db, job["id"], token):
                        lost.set()
                        return
            except Exception:  # noqa: BLE001 — a missed beat is retried next tick
                log.warning("heartbeat failed for job %s", job["id"])

    beater = threading.Thread(target=beat, daemon=True)
    beater.start()
    result: Any = None
    error: str | None = None
    try:
        handler = HANDLERS[job["kind"]]
        ctx = JobContext(job["id"], database_url, job["created_by"], lost.is_set)
        result = handler(loads(job["payload"], {}), ctx)
    except AppError as exc:
        error = str(exc.detail)
    except Exception as exc:  # noqa: BLE001
        log.exception("job %s failed", job["id"])
        error = scrub(f"{type(exc).__name__}: {exc}")
    finally:
        done.set()
        beater.join(timeout=2)
    if lost.is_set():
        log.warning("job %s lost its lease; result dropped", job["id"])
        return True
    with transaction(database_url) as db:
        jobs.finish(db, job["id"], token, result=result, error=error)
    log.info("job %s %s", job["id"], "failed" if error else "succeeded")
    return True


def _loop(database_url: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            worked = process_one(database_url)
        except Exception:  # noqa: BLE001
            log.exception("worker iteration failed; lease expiry will recover")
            worked = False
        if not worked:
            stop.wait(1)


def _presence(database_url: str, worker_id: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with transaction(database_url) as db:
                db.execute("DELETE FROM worker_heartbeats WHERE id=?", (worker_id,))
                db.execute(
                    "INSERT INTO worker_heartbeats (id, host, last_seen, started_at)"
                    " VALUES (?,?,?,?)",
                    (worker_id, socket.gethostname()[:255], time.time(), stamp()),
                )
        except Exception:  # noqa: BLE001
            log.warning("presence update failed")
        stop.wait(jobs.HEARTBEAT_SECONDS)
    with transaction(database_url) as db:
        db.execute("DELETE FROM worker_heartbeats WHERE id=?", (worker_id,))


def serve(database_url: str, stop: threading.Event, concurrency: int) -> None:
    worker_id = uid()
    threads = [threading.Thread(target=_presence, args=(database_url, worker_id, stop))]
    threads += [
        threading.Thread(target=_loop, args=(database_url, stop), daemon=True)
        for _ in range(concurrency)
    ]
    for thread in threads:
        thread.start()
    log.info("worker %s up · %d slot(s)", worker_id[:8], concurrency)
    for thread in threads:
        thread.join()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    settings.require_safe_runtime()
    check_schema(settings.database_url)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    serve(settings.database_url, stop, settings.worker_concurrency)


if __name__ == "__main__":
    main()
