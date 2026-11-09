"""Job handlers: kind → callable(payload, context) -> JSON-serialisable result.

Handlers run outside any transaction and may take minutes. Raise to fail the
job; the message is stored on the job row (keep it secret-free).

CHECKS validate a payload submitted over the API before it is queued, so a bad
one is rejected with 422 instead of failing later in the worker.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import Unprocessable
from app.schemas.models import RunPrompt
from app.services import runs


@dataclass(frozen=True)
class JobContext:
    job_id: str
    database_url: str
    user_id: str | None
    lost: Callable[[], bool]  # True once the lease is gone — stop early, don't write


def llm_run(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    """Payload = a RunPrompt: {prompt_key, variables, provider_id, model, …}."""
    result = runs.run(
        RunPrompt.model_validate(payload),
        database_url=ctx.database_url,
        source="job",
        user_id=ctx.user_id,
        job_id=ctx.job_id,
        stop=ctx.lost,  # cancelled (or lease lost): no new request or retry starts
    )
    return result.public()


def check_llm_run(payload: dict[str, Any]) -> None:
    try:
        RunPrompt.model_validate(payload)
    except ValidationError as exc:
        fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in exc.errors())
        raise Unprocessable(f"Invalid llm.run payload: {fields}.") from None


HANDLERS: dict[str, Callable[[dict[str, Any], JobContext], Any]] = {
    "llm.run": llm_run,
}

CHECKS: dict[str, Callable[[dict[str, Any]], None]] = {
    "llm.run": check_llm_run,
}
