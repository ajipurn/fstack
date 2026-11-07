"""One model call through llmfy, with usage captured even when the call fails."""

import time
import warnings
from dataclasses import dataclass

from llmfy import LLMfy, llmfy_usage_tracker

from app.llm.backends import ModelSpec, Usage, build_model, model_ids, secret_values, usage_from
from app.llm.errors import public_message, retryable
from app.llm.templates import normalize, placeholders


@dataclass(frozen=True)
class Completion:
    text: str
    usage: Usage
    latency_ms: int


class CallFailed(Exception):
    """Carries a safe message plus whatever usage the provider reported."""

    def __init__(
        self, message: str, usage: Usage, latency_ms: int, *, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.message = message
        self.usage = usage
        self.latency_ms = latency_ms
        self.retryable = retryable  # safe to try again: the provider never processed it


@dataclass(frozen=True)
class Catalog:
    models: list[str]
    latency_ms: int


def list_models(spec: ModelSpec) -> Catalog:
    """The provider's model list: doubles as a connection test that costs no tokens."""
    started = time.monotonic()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            models = model_ids(spec)
    except Exception as exc:  # noqa: BLE001 — every failure becomes a safe CallFailed
        elapsed = round((time.monotonic() - started) * 1000)
        raise CallFailed(public_message(exc, secret_values(spec.secret)), Usage(), elapsed) from exc
    return Catalog(models, round((time.monotonic() - started) * 1000))


def complete(
    spec: ModelSpec, system: str, user: str, variables: dict[str, str] | None = None
) -> Completion:
    """`system` may hold {{placeholders}} (rendered by llmfy); `user` is final text.

    A fresh LLMfy + usage tracker per call: no shared state between requests.
    """
    variables = variables or {}
    system = normalize(system)
    used = placeholders(system)
    started = time.monotonic()
    usage = Usage()
    try:
        model = build_model(spec)
        agent = LLMfy(model, system_message=system or None, input_variables=used or None)
        # llmfy warns for models missing from its bundled price list; we price
        # calls ourselves from models.dev, so those warnings are noise.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with llmfy_usage_tracker() as tracker:
                try:
                    result = agent.invoke(user, **{k: variables.get(k, "") for k in used})
                finally:
                    usage = usage_from(tracker.details, spec.kind)
        text = (result.result.content or "").strip()
    except Exception as exc:  # noqa: BLE001 — every failure becomes a recorded CallFailed
        elapsed = round((time.monotonic() - started) * 1000)
        message = public_message(exc, secret_values(spec.secret))
        raise CallFailed(message, usage, elapsed, retryable=retryable(exc)) from exc
    return Completion(text, usage, round((time.monotonic() - started) * 1000))
