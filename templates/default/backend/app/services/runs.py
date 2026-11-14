"""Running a prompt: the one entry point application code uses to call a model.

    result = runs.run_prompt(
        "summarize", {"text": body}, provider="OpenAI", model="gpt-5.4-mini", user_id=customer_id
    )

Every run names its prompt, provider (id or name) and model. Temperature and max
output tokens are optional: left out, the provider's own default for that model
applies. Anthropic requires max_tokens, so it gets the model's output limit from
the models.dev catalog.

Failures the provider never processed (rate limit, overload, connection refused)
are retried up to `retries` times with exponential backoff; timeouts never are,
since the request may have run. `stop` ends a run early: no new request or retry
starts once it returns True (one already sent still finishes — it may be billed).

Config is resolved in a short transaction, the provider is called outside any
transaction, and every attempt — success or failure — lands in llm_calls with
tokens, cost, latency and the exact prompt version.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.core.exceptions import Cancelled, Conflict, NotFound, ProviderError, Unprocessable
from app.db.session import Connection, transaction
from app.llm import output as structured
from app.llm.backends import ModelSpec, Usage, default_catalog
from app.llm.client import CallFailed, Completion, complete
from app.llm.outputs import OUTPUTS
from app.llm.templates import as_text, missing, placeholders, render
from app.schemas.models import RunPrompt
from app.services import calls, pricing, providers

# Used only when Anthropic is asked for a model the catalog has no output limit for.
ANTHROPIC_MAX_TOKENS = 4096
# Wait before retry n (±25% jitter so parallel runs don't retry in lockstep).
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)

Stop = Callable[[], bool]


def never() -> bool:
    return False


@dataclass
class Plan:
    prompt_key: str
    output: type[BaseModel] | None
    provider: dict[str, Any]
    model_spec: ModelSpec
    version: dict[str, Any]
    rates: pricing.Rates | None


@dataclass
class RunResult:
    prompt: str
    text: str
    data: dict[str, Any] | None
    usage: Usage
    cost_usd: float | None
    latency_ms: int
    model: str
    provider: str
    prompt_version: int
    prompt_digest: str
    call_ids: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "text": self.text,
            "data": self.data,
            "usage": vars(self.usage) | {"total_tokens": self.usage.total},
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "provider": self.provider,
            "prompt_version": self.prompt_version,
            "prompt_digest": self.prompt_digest,
            "call_ids": self.call_ids,
            "attempts": len(self.call_ids),
        }


def resolve(db: Connection, run: RunPrompt) -> Plan:
    provider = providers.find_row(db, run.provider_id)
    if not provider["enabled"]:
        raise Conflict(f"Provider '{provider['name']}' is disabled.")
    if run.prompt_version_id:
        version = db.execute(
            "SELECT * FROM fstack_prompt_versions WHERE id=? AND prompt_key=?",
            (run.prompt_version_id, run.prompt_key),
        ).fetchone()
        if not version:
            raise NotFound("That prompt version doesn't exist.")
    else:
        if not db.execute(
            "SELECT 1 FROM fstack_prompts WHERE `key`=?", (run.prompt_key,)
        ).fetchone():
            raise NotFound(f"Prompt '{run.prompt_key}' not found.")
        version = db.execute(
            "SELECT v.* FROM fstack_prompts p"
            " JOIN fstack_prompt_versions v ON v.id = p.active_version_id WHERE p.`key`=?",
            (run.prompt_key,),
        ).fetchone()
        if not version:
            raise Unprocessable(f"Prompt '{run.prompt_key}' has no active version. Publish one.")
    catalog_id = provider["catalog_id"] or default_catalog(provider["kind"], provider["base_url"])
    rates = pricing.find_rates(db, catalog_id, run.model)
    max_tokens = run.max_tokens
    if max_tokens is None and provider["kind"] == "anthropic":
        max_tokens = (rates.output_limit if rates else None) or ANTHROPIC_MAX_TOKENS
    return Plan(
        prompt_key=run.prompt_key,
        output=OUTPUTS.get(run.prompt_key),
        provider=provider,
        model_spec=providers.spec_for(
            provider, run.model, temperature=run.temperature, max_tokens=max_tokens
        ),
        version=dict(version),
        rates=rates,
    )


def run_prompt(
    prompt_key: str,
    variables: dict[str, Any] | None = None,
    *,
    provider: str,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    prompt_version_id: str | None = None,
    retries: int = 2,
    database_url: str | None = None,
    source: str = "api",
    user_id: str | None = None,
    job_id: str | None = None,
    stop: Stop = never,
) -> RunResult:
    """`provider` is a provider id or its name as shown in Configure → Providers."""
    body = RunPrompt(
        prompt_key=prompt_key,
        variables=variables or {},
        provider_id=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        prompt_version_id=prompt_version_id,
        retries=retries,
    )
    return run(
        body,
        database_url=database_url,
        source=source,
        user_id=user_id,
        job_id=job_id,
        stop=stop,
    )


def run(
    body: RunPrompt,
    *,
    database_url: str | None = None,
    source: str = "api",
    user_id: str | None = None,
    job_id: str | None = None,
    stop: Stop = never,
) -> RunResult:
    with transaction(database_url) as db:
        plan = resolve(db, body)

    version = plan.version
    required = placeholders(version["system"], version["user_template"])
    absent = missing(required, body.variables)
    if absent:
        raise Unprocessable(f"Missing variables: {', '.join(absent)}.")
    text_values = {name: as_text(body.variables[name]) for name in required}
    system = version["system"]
    if plan.output:
        system += structured.schema_instructions(plan.output)
    user = render(version["user_template"], text_values)

    record = Recorder(plan, database_url, source, user_id, job_id)
    attempts = 2 if plan.output else 1
    total = Usage()
    cost: float | None = 0.0
    latency = 0
    feedback = ""
    for attempt in range(attempts):
        prompt_system = system + (structured.correction(feedback) if feedback else "")
        request = {"system": prompt_system, "user": user}
        completion = _complete(plan, prompt_system, user, text_values, request, record, body, stop)
        total = _add(total, completion.usage)
        latency += completion.latency_ms
        call_cost = pricing.cost_usd(plan.rates, completion.usage)
        cost = None if cost is None or call_cost is None else cost + call_cost
        data = None
        error = None
        if plan.output:
            try:
                data = structured.parse(plan.output, completion.text)
            except structured.OutputInvalid as invalid:
                feedback = invalid.feedback
                error = f"Invalid output: {invalid.feedback}"[:1000]
        status = "error" if error else "ok"
        record(completion.usage, completion.latency_ms, status, error, request, completion.text)
        if error is None:
            return RunResult(
                prompt=plan.prompt_key,
                text=completion.text,
                data=data,
                usage=total,
                cost_usd=cost,
                latency_ms=latency,
                model=plan.model_spec.model,
                provider=plan.provider["name"],
                prompt_version=version["version"],
                prompt_digest=version["digest"],
                call_ids=record.call_ids,
            )
        if attempt == attempts - 1:
            raise Unprocessable(f"The model kept returning invalid JSON: {feedback}")
    raise AssertionError("unreachable")


def _complete(
    plan: Plan,
    system: str,
    user: str,
    values: dict[str, str],
    request: dict[str, str],
    record: "Recorder",
    body: RunPrompt,
    stop: Stop,
) -> Completion:
    """One answer from the provider, retrying only failures it never processed."""
    for attempt in range(body.retries + 1):
        if stop():
            raise Cancelled("Run stopped.")
        try:
            return complete(plan.model_spec, system, user, values)
        except CallFailed as failure:
            record(failure.usage, failure.latency_ms, "error", failure.message, request)
            if not failure.retryable or attempt == body.retries:
                raise ProviderError(failure.message) from None
        if _pause(BACKOFF_SECONDS[attempt] * random.uniform(0.75, 1.25), stop):
            raise Cancelled("Run stopped.")
    raise AssertionError("unreachable")


def _pause(seconds: float, stop: Stop) -> bool:
    """Sleep, waking early to stop. True = stopped."""
    deadline = time.monotonic() + seconds
    while (left := deadline - time.monotonic()) > 0:
        if stop():
            return True
        time.sleep(min(0.25, left))
    return stop()


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(
        a.input_tokens + b.input_tokens,
        a.output_tokens + b.output_tokens,
        a.cache_read_tokens + b.cache_read_tokens,
        a.cache_write_tokens + b.cache_write_tokens,
    )


class Recorder:
    """Writes one llm_calls row per attempt, each in its own short transaction."""

    def __init__(
        self,
        plan: Plan,
        database_url: str | None,
        source: str,
        user_id: str | None,
        job_id: str | None,
    ) -> None:
        self.plan = plan
        self.database_url = database_url
        self.source = source
        self.user_id = user_id
        self.job_id = job_id
        self.call_ids: list[str] = []

    def __call__(
        self,
        usage: Usage,
        latency_ms: int,
        status: str,
        error: str | None,
        request: dict[str, str],
        response: str | None = None,
    ) -> None:
        plan = self.plan
        with transaction(self.database_url) as db:
            call_id = calls.record(
                db,
                provider=plan.provider,
                model=plan.model_spec.model,
                prompt_key=plan.prompt_key,
                version=plan.version,
                usage=usage,
                cost_usd=pricing.cost_usd(plan.rates, usage),
                rates=plan.rates,
                latency_ms=latency_ms,
                status=status,
                error=error,
                source=self.source,
                user_id=self.user_id,
                job_id=self.job_id,
                request=request,
                response=response,
            )
        self.call_ids.append(call_id)
