"""Turn provider failures into short, secret-free messages."""

import re

import llmfy

_BEARER = re.compile(r"(?i)(bearer\s+)\S+")
_ASSIGNED = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?key|secret|password|token|x-api-key)\s*[:=]\s*)\S+"
)
_KEY_LIKE = re.compile(r"\b(?:sk-|sk_|xai-|gsk_|AKIA|ABSK|AIza)[A-Za-z0-9+/=_-]{8,}")

_MESSAGES: tuple[tuple[type[Exception], str], ...] = (
    (llmfy.AuthenticationException, "The provider rejected the credentials."),
    (llmfy.PermissionDeniedException, "The provider denied access to this model."),
    (llmfy.ModelNotFoundException, "The model was not found at this provider."),
    (llmfy.QuotaExceededException, "The provider quota was exceeded."),
    (llmfy.RateLimitException, "The provider rate-limited the request."),
    (llmfy.TimeoutException, "The provider request timed out."),
    (llmfy.ServiceUnavailableException, "The provider is temporarily unavailable."),
    (llmfy.ContentFilterException, "The provider blocked the request as unsafe."),
    (llmfy.InvalidRequestException, "The provider rejected the request."),
    (llmfy.ModelErrorException, "The model failed while generating."),
)


# Failures the provider never processed, so trying again can't double-bill: rate
# limits, overload / unavailable (llmfy maps connection errors and 5xx here). Not
# timeouts — the request may have run — and not quota, which won't recover.
_RETRYABLE = (llmfy.RateLimitException, llmfy.ServiceUnavailableException)
_RETRYABLE_NAMES = {
    "RateLimitError",
    "InternalServerError",
    "APIConnectionError",
    "OverloadedError",
}
_RETRYABLE_STATUS = {429, 500, 502, 503, 529}


def retryable(exc: BaseException) -> bool:
    if isinstance(exc, llmfy.TimeoutException) or "Timeout" in type(exc).__name__:
        return False
    if isinstance(exc, _RETRYABLE) or type(exc).__name__ in _RETRYABLE_NAMES:
        return True
    return getattr(exc, "status_code", None) in _RETRYABLE_STATUS


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    cleaned = " ".join(str(text).split())
    for secret in secrets:
        if secret and len(secret) >= 6:
            cleaned = cleaned.replace(secret, "[redacted]")
    cleaned = _BEARER.sub(r"\1[redacted]", cleaned)
    cleaned = _ASSIGNED.sub(r"\1[redacted]", cleaned)
    cleaned = _KEY_LIKE.sub("[redacted]", cleaned)
    return cleaned[:500]


def public_message(exc: BaseException, secrets: tuple[str, ...] = ()) -> str:
    for kind, message in _MESSAGES:
        if isinstance(exc, kind):
            detail = scrub(str(exc), secrets)
            return f"{message} {detail}".strip() if detail else message
    return scrub(f"{type(exc).__name__}: {exc}", secrets) or "The provider request failed."
