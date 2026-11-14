"""Request bodies. Validators raise ValueError with user-facing text."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.llm.backends import WORKERS_AI_URL
from app.llm.templates import check_template, placeholders


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── auth ─────────────────────────────────────────────────────────────────────


class Login(Model):
    key: str = Field(min_length=1, max_length=512)


# ── providers ────────────────────────────────────────────────────────────────

ProviderKind = Literal["openai", "anthropic", "bedrock", "google"]


class ProviderWrite(Model):
    name: str = Field(min_length=1, max_length=160)
    kind: ProviderKind
    protocol: Literal["chat", "responses"] = "chat"
    base_url: str = Field(default="", max_length=500)
    region: str = Field(default="", max_length=60)
    catalog_id: str = Field(default="", max_length=80)
    # Filled from the provider's model list ("Load models"), not typed in.
    models: list[str] = Field(default_factory=list, max_length=2000)
    enabled: bool = True
    # Blank secret fields keep the stored secret on update.
    api_key: str = Field(default="", max_length=4000)
    aws_access_key_id: str = Field(default="", max_length=200)
    aws_secret_access_key: str = Field(default="", max_length=400)

    @field_validator("models")
    @classmethod
    def unique_models(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(m.strip() for m in value if m.strip()))
        if any(len(m) > 200 for m in cleaned):
            raise ValueError("Model ids must be at most 200 characters.")
        return cleaned

    @model_validator(mode="after")
    def per_kind(self) -> "ProviderWrite":
        if self.base_url:
            if not re.match(r"^https?://[^\s/?#]+[^\s?#]*$", self.base_url):
                raise ValueError("Base URL must be an http(s) URL without query or fragment.")
            self.base_url = self.base_url.rstrip("/")
            if re.search(r"/(chat/completions|responses|messages)$", self.base_url):
                raise ValueError("Use the API root as base URL, e.g. https://api.openai.com/v1.")
            cloudflare = re.match(r"^https?://api\.cloudflare\.com(/|$)", self.base_url, re.I)
            if self.kind == "openai" and cloudflare and not WORKERS_AI_URL.match(self.base_url):
                raise ValueError(
                    "Workers AI's base URL is https://api.cloudflare.com/client/v4/accounts/"
                    "<account id>/ai/v1, with your 32-character account id."
                )
        if self.kind == "bedrock" and not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", self.region):
            raise ValueError("Bedrock needs an AWS region such as us-east-1.")
        if self.kind != "openai":
            self.protocol = "chat"
        return self


class ProviderUpdate(ProviderWrite):
    revision: int = Field(ge=1)


class ProviderProbe(ProviderWrite):
    provider_id: str = ""  # reuse the stored secret for an unsaved edit
    model: str = ""


# ── prompts ──────────────────────────────────────────────────────────────────


class PromptBody(Model):
    system: str = Field(default="", max_length=100_000)
    # The user message the model receives; usually carries the input variables.
    user_template: str = Field(min_length=1, max_length=100_000)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def templates(self) -> "PromptBody":
        check_template(self.system)
        check_template(self.user_template)
        return self

    @property
    def variables(self) -> list[str]:
        return placeholders(self.system, self.user_template)


class PromptCreate(PromptBody):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,79}$")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)


class PromptMeta(Model):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    revision: int = Field(ge=1)


class DraftSave(PromptBody):
    revision: int = Field(ge=1)


class Publish(Model):
    revision: int = Field(ge=1)
    note: str = Field(default="", max_length=500)
    activate: bool = True


class Activate(Model):
    version_id: str


# ── runs ─────────────────────────────────────────────────────────────────────


class RunPrompt(Model):
    """One run: a prompt, a provider and a model. Everything else is optional."""

    prompt_key: str = Field(min_length=1, max_length=80)
    variables: dict[str, Any] = Field(default_factory=dict)
    provider_id: str = Field(min_length=1, max_length=160)  # id, or the provider's name
    model: str = Field(min_length=1, max_length=200)
    prompt_version_id: str | None = None  # default: the prompt's active version
    # None = the model's own default.
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    # Extra tries for failures the provider never processed (rate limit, overload).
    retries: int = Field(default=2, ge=0, le=5)


# ── models / jobs ────────────────────────────────────────────────────────────


class ManualPrice(Model):
    catalog_id: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=200)
    input: float = Field(ge=0, le=100_000)
    output: float = Field(ge=0, le=100_000)
    cache_read: float | None = Field(default=None, ge=0, le=100_000)
    cache_write: float | None = Field(default=None, ge=0, le=100_000)


class JobCreate(Model):
    kind: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
