import asyncio
import threading

from fastapi import APIRouter, Request

from app.api.deps import Actor, DatabaseUrl
from app.core.exceptions import Cancelled
from app.schemas.models import RunPrompt
from app.services import runs

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
async def run_prompt(body: RunPrompt, request: Request, url: DatabaseUrl, actor: Actor):
    """Synchronous run (dashboard, scripts). It works in a thread, outside any
    transaction. Closing the request — the dashboard's Stop aborts it — stops the run:
    no new provider request or retry starts (one already sent finishes and is
    recorded, since it may be billed)."""
    stop = threading.Event()
    source = "dashboard" if actor["id"] == "dashboard" else "api"
    work = asyncio.ensure_future(
        asyncio.to_thread(
            runs.run, body, database_url=url, source=source, user_id=actor["id"], stop=stop.is_set
        )
    )
    # Once the client is gone nobody awaits the thread; collect its outcome quietly.
    work.add_done_callback(lambda done: done.cancelled() or done.exception())
    while True:
        finished, _ = await asyncio.wait({work}, timeout=0.25)
        if finished:
            return work.result().public()
        if await request.is_disconnected():
            stop.set()
            raise Cancelled("Run stopped.")
