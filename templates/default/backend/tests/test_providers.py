import httpx
from fastapi.testclient import TestClient

from app.db.session import transaction
from app.llm import backends
from app.services import pricing
from tests.conftest import MODELS_DEV, FakeOpenAI, add_provider


def test_test_connection_loads_and_caches_the_model_list(
    client: TestClient, fake_openai: FakeOpenAI
) -> None:
    provider = add_provider(client, models=[])
    result = client.post(
        "/api/providers/probe",
        json={
            "provider_id": provider["id"],
            "name": provider["name"],
            "kind": "openai",
            "base_url": provider["base_url"],
        },
    ).json()
    # Sorted, embeddings dropped, and no completion was spent on it.
    assert result["ok"] and result["models"] == ["gpt-test-large", "gpt-test-mini"]
    assert fake_openai.requests == []
    saved = next(p for p in client.get("/api/providers").json() if p["id"] == provider["id"])
    assert saved["models"] == result["models"] and saved["last_test_ok"] is True
    # Refreshing the list isn't an edit: an editor opened before can still save.
    assert saved["revision"] == provider["revision"]


def test_a_draft_provider_lists_models_without_any_typed_in(
    client: TestClient, fake_openai: FakeOpenAI
) -> None:
    result = client.post(
        "/api/providers/probe",
        json={
            "name": "Draft",
            "kind": "openai",
            "base_url": "https://api.openai.test/v1",
            "api_key": "sk-test-abcdef123456",
        },
    ).json()
    assert result["ok"] and "2 models" in result["message"]


class FakeBedrock:
    def list_inference_profiles(self, **_: object) -> dict:
        return {
            "inferenceProfileSummaries": [
                {"inferenceProfileId": "us.anthropic.claude-test", "status": "ACTIVE"}
            ]
        }

    def list_foundation_models(self, **_: object) -> dict:
        return {
            "modelSummaries": [
                {"modelId": "amazon.nova-test-v1:0", "inferenceTypesSupported": ["ON_DEMAND"]},
                # Profile-only and retired models can't be called directly.
                {"modelId": "anthropic.claude-x", "inferenceTypesSupported": ["INFERENCE_PROFILE"]},
                {
                    "modelId": "old.model-v1",
                    "inferenceTypesSupported": ["ON_DEMAND"],
                    "modelLifecycle": {"status": "LEGACY"},
                },
            ]
        }


def test_bedrock_lists_inference_profiles_and_on_demand_models(monkeypatch) -> None:
    monkeypatch.setattr(backends, "_aws_client", lambda spec, service: FakeBedrock())
    spec = backends.ModelSpec(
        kind="bedrock",
        protocol="chat",
        model="",
        base_url="",
        region="us-east-1",
        secret={},
        temperature=None,
        max_tokens=16,
        timeout=5,
    )
    assert backends.model_ids(spec) == ["amazon.nova-test-v1:0", "us.anthropic.claude-test"]


# ── Cloudflare Workers AI ────────────────────────────────────────────────────

ACCOUNT = "0123456789abcdef0123456789abcdef"
WORKERS_AI = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/v1"
CF_TOKEN = "cf-token-0123456789abcdef"


def workers_ai(handler, monkeypatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        backends,
        "_http_client",
        lambda spec: httpx.Client(transport=httpx.MockTransport(recording)),
    )
    return seen


def catalog_page(request: httpx.Request) -> httpx.Response:
    pages = {
        "1": [
            {"name": "@cf/meta/llama-test", "task": {"name": "Text Generation"}},
            {"name": "@cf/baai/bge-test", "task": {"name": "Text Embeddings"}},
        ],
        "2": [{"name": "@cf/qwen/qwen-test", "task": {"name": "Text Generation"}}],
    }
    result = pages.get(request.url.params["page"], [])
    return httpx.Response(200, json={"success": True, "errors": [], "result": result})


def test_workers_ai_lists_text_models_from_the_account_catalog(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(backends, "_WORKERS_AI_PAGE", 2)
    seen = workers_ai(catalog_page, monkeypatch)
    body = {"name": "Workers AI", "kind": "openai", "base_url": WORKERS_AI, "api_key": CF_TOKEN}
    result = client.post("/api/providers/probe", json=body).json()
    assert result["ok"] and result["models"] == ["@cf/meta/llama-test", "@cf/qwen/qwen-test"]
    # Same host and account as the runs, and the page after a short one is never asked for.
    assert [str(r.url.copy_with(query=None)) for r in seen] == [
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/models/search"
    ] * 2
    assert all(r.headers["authorization"] == f"Bearer {CF_TOKEN}" for r in seen)


def test_workers_ai_errors_are_shown_without_the_token(client: TestClient, monkeypatch) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        error = {"code": 10000, "message": "Authentication error"}
        return httpx.Response(401, json={"success": False, "errors": [error], "result": None})

    workers_ai(refused, monkeypatch)
    body = {"name": "Workers AI", "kind": "openai", "base_url": WORKERS_AI, "api_key": CF_TOKEN}
    result = client.post("/api/providers/probe", json=body).json()
    assert result["ok"] is False and "401: Authentication error" in result["message"]
    assert result["message"].startswith("The provider rejected the credentials.")
    assert CF_TOKEN not in result["message"]

    keyless = client.post("/api/providers/probe", json={**body, "api_key": ""}).json()
    assert keyless["ok"] is False and "Enter an API key" in keyless["message"]


def test_workers_ai_needs_the_account_url(client: TestClient) -> None:
    body = {"name": "Workers AI", "kind": "openai", "api_key": CF_TOKEN}
    for url in (
        "https://api.cloudflare.com/client/v4/accounts//ai/v1",
        "https://api.cloudflare.com",
    ):
        response = client.post("/api/providers", json={**body, "base_url": url})
        assert response.status_code == 422 and "account id" in response.text


def test_workers_ai_prices_from_its_own_catalog_by_default(
    client: TestClient, database: str, monkeypatch
) -> None:
    cloudflare = {
        "cloudflare-workers-ai": {
            "id": "cloudflare-workers-ai",
            "models": {
                "@cf/meta/llama-test": {
                    "id": "@cf/meta/llama-test",
                    "cost": {"input": 0.3, "output": 0.6},
                }
            },
        }
    }
    monkeypatch.setattr(pricing, "fetch_catalog", lambda url=None: {**MODELS_DEV, **cloudflare})
    provider = add_provider(client, name="Workers AI", base_url=WORKERS_AI, catalog_id="")
    assert provider["catalog_id"] == "cloudflare-workers-ai"
    with transaction(database) as db:
        assert pricing.find_rates(db, "cloudflare-workers-ai", "@cf/meta/llama-test").input == 0.3
