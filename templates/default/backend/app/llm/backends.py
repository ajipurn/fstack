"""Provider kind → llmfy model. The only module that knows SDK specifics.

Retries are owned by the application (an ambiguous failure may already be
billed), so every SDK client is rebuilt with retries off and our timeout.
"""

import re
from dataclasses import dataclass, replace
from typing import Any

import llmfy
from llmfy.llmfy_core.llms.base_ai_model import BaseAIModel

KINDS = ("openai", "anthropic", "bedrock", "google")

# OpenAI-style catalogs list every model; these are clearly not text generation.
_NOT_TEXT = re.compile(
    r"embed|tts|whisper|dall-e|davinci|babbage|moderation|transcri|realtime|audio|image|sora",
    re.IGNORECASE,
)
MAX_MODELS = 2000

# models.dev provider ids used for pricing when the provider row leaves catalog_id empty.
DEFAULT_CATALOG = {
    "openai": "openai",
    "anthropic": "anthropic",
    "bedrock": "amazon-bedrock",
    "google": "google",
}


@dataclass(frozen=True)
class ModelSpec:
    kind: str
    protocol: str  # chat | responses (openai only)
    model: str
    base_url: str
    region: str
    secret: dict[str, str]
    temperature: float | None  # None = the model's default (not sent)
    max_tokens: int | None  # None = the model's default (not sent)
    timeout: float


@dataclass(frozen=True)
class Usage:
    """Normalised so `input_tokens` always INCLUDES cached tokens."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


def build_model(spec: ModelSpec) -> BaseAIModel:
    if spec.kind == "openai":
        return _openai(spec)
    if spec.kind == "anthropic":
        return _anthropic(spec)
    if spec.kind == "bedrock":
        return _bedrock(spec)
    if spec.kind == "google":
        return _google(spec)
    raise ValueError(f"Unsupported provider kind: {spec.kind}")


def _openai(spec: ModelSpec) -> BaseAIModel:
    key = spec.secret.get("api_key") or "not-needed"  # local servers (Ollama, vLLM) accept any key
    base_url = spec.base_url or None
    model: Any
    if spec.protocol == "responses":
        model = llmfy.OpenAIResponsesModel(
            model=spec.model,
            config=llmfy.OpenAIResponsesConfig(
                temperature=spec.temperature, top_p=None, max_output_tokens=spec.max_tokens
            ),
            api_key=key,
            base_url=base_url,
        )
    else:
        model = llmfy.OpenAIChatModel(
            model=spec.model,
            config=llmfy.OpenAIChatConfig(
                temperature=spec.temperature, top_p=None, max_tokens=spec.max_tokens
            ),
            api_key=key,
            base_url=base_url,
        )
    model.client = model.client.with_options(timeout=spec.timeout, max_retries=0)
    return model


def _anthropic(spec: ModelSpec) -> BaseAIModel:
    model: Any = llmfy.AnthropicMessagesModel(
        model=spec.model,
        # The Messages API requires max_tokens; runs fill in the model's output limit.
        config=llmfy.AnthropicMessagesConfig(
            temperature=spec.temperature, max_tokens=spec.max_tokens or 4096
        ),
        api_key=spec.secret.get("api_key"),
        base_url=spec.base_url or None,
    )
    model.client = model.client.with_options(timeout=spec.timeout, max_retries=0)
    return model


def _aws_client(spec: ModelSpec, service: str) -> Any:
    """boto3 client with our timeout and no retries; blank keys = default credential chain."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        service,
        aws_access_key_id=spec.secret.get("aws_access_key_id") or None,
        aws_secret_access_key=spec.secret.get("aws_secret_access_key") or None,
        region_name=spec.region or "us-east-1",
        config=Config(
            connect_timeout=10,
            read_timeout=spec.timeout,
            retries={"total_max_attempts": 1},
        ),
    )


def _bedrock(spec: ModelSpec) -> BaseAIModel:
    access = spec.secret.get("aws_access_key_id") or None
    secret = spec.secret.get("aws_secret_access_key") or None
    region = spec.region or "us-east-1"
    model: Any = llmfy.BedrockConverseModel(
        model=spec.model,
        # Newer Claude models reject temperature + top_p together.
        config=llmfy.BedrockConverseConfig(
            temperature=spec.temperature, top_p=None, max_tokens=spec.max_tokens
        ),
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        aws_bedrock_region=region,
    )
    model.client.close()
    model.client = _aws_client(spec, "bedrock-runtime")
    return model


def _google(spec: ModelSpec) -> BaseAIModel:
    from google import genai
    from google.genai import types

    config = llmfy.GoogleAIGenerateConfig(max_tokens=spec.max_tokens)
    # llmfy types temperature as float (default 0.7); None reaches the SDK as
    # "unset", which leaves the model's own default in place.
    config.temperature = spec.temperature  # type: ignore[assignment]
    model: Any = llmfy.GoogleAIGenerateModel(
        model=spec.model, config=config, api_key=spec.secret.get("api_key")
    )
    model.client = genai.Client(
        api_key=spec.secret.get("api_key"),
        http_options=types.HttpOptions(timeout=int(spec.timeout * 1000)),
    )
    return model


def model_ids(spec: ModelSpec) -> list[str]:
    """Text models the endpoint serves, sorted. Lists only: never generates text.

    Uses the same clients as generation (timeout, retries off), so the stored
    key only ever goes to the endpoint it was saved for.
    """
    listing = replace(spec, model=spec.model or "list-models")  # SDK wrappers want a name
    if spec.kind == "openai":
        ids = [m.id for m in _openai(listing).client.models.list()]  # type: ignore[attr-defined]
        ids = [i for i in ids if not _NOT_TEXT.search(i)]
    elif spec.kind == "anthropic":
        ids = [m.id for m in _anthropic(listing).client.models.list(limit=1000)]  # type: ignore[attr-defined]
    elif spec.kind == "google":
        ids = [
            (m.name or "").removeprefix("models/")
            for m in _google(listing).client.models.list()  # type: ignore[attr-defined]
            if "generateContent" in (m.supported_actions or [])
        ]
    elif spec.kind == "bedrock":
        ids = _bedrock_model_ids(spec)
    else:
        raise ValueError(f"Unsupported provider kind: {spec.kind}")
    return sorted({i for i in ids if 0 < len(i) <= 200})[:MAX_MODELS]


def _bedrock_model_ids(spec: ModelSpec) -> list[str]:
    """Inference profiles (us.anthropic.…, needed by newer models) + on-demand models."""
    from botocore.exceptions import ClientError

    client = _aws_client(spec, "bedrock")
    ids: list[str] = []
    token: str | None = None
    try:
        for _ in range(20):
            more = {"nextToken": token} if token else {}
            page = client.list_inference_profiles(
                maxResults=1000, typeEquals="SYSTEM_DEFINED", **more
            )
            ids += [
                p["inferenceProfileId"]
                for p in page.get("inferenceProfileSummaries", [])
                if p.get("status") == "ACTIVE"
            ]
            token = page.get("nextToken")
            if not token:
                break
    except ClientError as exc:  # no bedrock:ListInferenceProfiles: on-demand models still list
        if exc.response.get("Error", {}).get("Code") != "AccessDeniedException":
            raise
    for summary in client.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]:
        active = summary.get("modelLifecycle", {}).get("status", "ACTIVE") == "ACTIVE"
        if active and "ON_DEMAND" in summary.get("inferenceTypesSupported", []):
            ids.append(summary["modelId"])
    return ids


def usage_from(details: list[dict[str, Any]], kind: str) -> Usage:
    """Sum llmfy's per-request usage details into one normalised Usage.

    OpenAI/Google report input tokens *including* cache hits; Anthropic and
    Bedrock Converse report them separately — fold those back in.
    """
    totals = {"input": 0, "output": 0, "read": 0, "write": 0}
    for detail in details:
        totals["input"] += int(detail.get("input_tokens") or 0)
        totals["output"] += int(detail.get("output_tokens") or 0)
        totals["read"] += int(detail.get("cache_read_tokens") or 0)
        totals["write"] += int(detail.get("cache_write_tokens") or 0)
    input_tokens = totals["input"]
    if kind in ("anthropic", "bedrock"):
        input_tokens += totals["read"] + totals["write"]
    return Usage(input_tokens, totals["output"], totals["read"], totals["write"])


def secret_values(secret: dict[str, str]) -> tuple[str, ...]:
    return tuple(value for value in secret.values() if value)
