import base64
import json
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import ProviderError
from app.db.migrations import migrate
from app.db.session import engine_for, transaction
from app.llm import backends, outputs
from app.services import pricing, prompts

ACCESS_KEY = "test-access-key-0123456789-abcdefghij"
# The template ships no prompts; tests run against these two.
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv(
        "APP_ENCRYPTION_KEY", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    )
    monkeypatch.setenv("APP_LOG_LLM_PAYLOADS", "true")
    yield
    get_settings.cache_clear()


class Summary(BaseModel):
    title: str = Field(description="Short headline, at most 8 words")
    summary: str = Field(description="Two or three sentences")
    key_points: list[str] = Field(description="3-5 bullet points", max_length=8)
    sentiment: Literal["positive", "neutral", "negative", "mixed"]


@pytest.fixture(autouse=True)
def structured_summarize(monkeypatch: pytest.MonkeyPatch) -> None:
    """tests/prompts/summarize.md answers with typed JSON, the way a project would list it."""
    monkeypatch.setitem(outputs.OUTPUTS, "summarize", Summary)


@pytest.fixture(autouse=True)
def offline_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never download models.dev; saving a provider leaves prices as they are."""

    def offline(url: str | None = None) -> dict:
        raise ProviderError("models.dev is offline in tests.")

    monkeypatch.setattr(pricing, "fetch_catalog", offline)


@pytest.fixture()
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("APP_DATABASE_URL", url)
    get_settings.cache_clear()
    migrate(url)
    with transaction(url) as db:
        prompts.sync_files(db, PROMPTS_DIR)
    yield url
    engine_for.cache_clear()


@pytest.fixture()
def client(database: str) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app(database)) as test_client:
        response = test_client.post("/api/auth/login", json={"key": ACCESS_KEY})
        assert response.status_code == 200, response.text
        test_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield test_client


class FakeOpenAI:
    """Answers Chat Completions requests through httpx.MockTransport."""

    def __init__(self) -> None:
        self.replies: list[str] = []
        self.requests: list[dict] = []
        self.failures: list[int] = []  # HTTP statuses to answer with before succeeding
        self.usage = {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}

    catalog = ("gpt-test-mini", "text-embedding-test", "gpt-test-large")

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            data = [{"id": m, "object": "model", "created": 0} for m in self.catalog]
            return httpx.Response(200, json={"object": "list", "data": data})
        body = json.loads(request.content)
        self.requests.append(body)
        if self.failures:
            error = {"error": {"message": "simulated failure", "type": "test"}}
            return httpx.Response(self.failures.pop(0), json=error)
        content = self.replies.pop(0) if self.replies else "OK"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": self.usage,
            },
        )


@pytest.fixture()
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> FakeOpenAI:
    fake = FakeOpenAI()
    original = backends._openai

    def patched(spec: backends.ModelSpec):
        model = original(spec)
        model.client = model.client.with_options(
            http_client=httpx.Client(transport=httpx.MockTransport(fake.handler))
        )
        return model

    monkeypatch.setattr(backends, "_openai", patched)
    return fake


def add_provider(client: TestClient, **overrides) -> dict:
    body = {
        "name": "OpenAI",
        "kind": "openai",
        "base_url": "https://api.openai.test/v1",
        "models": ["gpt-test-mini"],
        "api_key": "sk-test-1234567890abcdef",
        "catalog_id": "openai",
        **overrides,
    }
    response = client.post("/api/providers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


MODELS_DEV = {
    "openai": {
        "id": "openai",
        "models": {
            "gpt-test-mini": {
                "id": "gpt-test-mini",
                "name": "GPT Test Mini",
                "cost": {"input": 0.25, "output": 2.0, "cache_read": 0.025},
                "limit": {"context": 400000, "output": 128000},
                "reasoning": True,
            }
        },
    },
    "anthropic": {
        "id": "anthropic",
        "models": {
            "claude-test": {
                "id": "claude-test",
                "name": "Claude Test",
                "cost": {
                    "input": 1.0,
                    "output": 5.0,
                    "cache_read": 0.1,
                    "cache_write": 1.25,
                    "tiers": [
                        {"input": 2.0, "output": 10.0, "tier": {"type": "context", "size": 200000}}
                    ],
                },
                "limit": {"context": 1000000, "output": 64000},
            }
        },
    },
    "amazon-bedrock": {
        "id": "amazon-bedrock",
        "models": {
            "anthropic.claude-test-v1:0": {
                "id": "anthropic.claude-test-v1:0",
                "name": "Claude Test (Bedrock)",
                "cost": {"input": 1.1, "output": 5.5},
            }
        },
    },
}
