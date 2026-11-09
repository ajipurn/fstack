"""Security regressions: access key, sessions, login throttle, stored keys, docs."""

import base64
import secrets

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db.session import transaction
from app.llm import backends
from app.llm.client import CallFailed, complete
from app.services import auth
from tests.conftest import ACCESS_KEY, add_provider

VARS = {"text": "hi", "tone": "calm"}


@pytest.fixture()
def anonymous(database: str):
    from app.main import create_app

    with TestClient(create_app(database)) as test_client:
        yield test_client


# ── access key ───────────────────────────────────────────────────────────────


def test_bearer_key_calls_the_api_without_csrf(anonymous: TestClient) -> None:
    headers = {"Authorization": f"Bearer {ACCESS_KEY}"}
    assert anonymous.get("/api/auth/me", headers=headers).json()["via"] == "api"
    created = anonymous.post(
        "/api/providers",
        headers=headers,
        json={"name": "OpenAI", "kind": "openai", "models": ["m"], "api_key": "sk-test-123456"},
    )
    assert created.status_code == 201, created.text


@pytest.mark.parametrize(
    "header", [f"Bearer {ACCESS_KEY}x", "Bearer ", f"Basic {ACCESS_KEY}", ACCESS_KEY]
)
def test_wrong_bearer_is_rejected(client: TestClient, header: str) -> None:
    # A bad Authorization header fails even when a valid session cookie is present.
    assert client.get("/api/providers", headers={"Authorization": header}).status_code == 401


def test_no_credentials_no_access(anonymous: TestClient) -> None:
    assert anonymous.get("/api/providers").status_code == 401
    assert anonymous.get("/api/auth/me").status_code == 401


def test_wrong_key_does_not_sign_in(anonymous: TestClient) -> None:
    response = anonymous.post("/api/auth/login", json={"key": "not-the-key"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_a_new_key_ends_old_sessions(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.get("/api/auth/me").status_code == 200
    monkeypatch.setenv("APP_ACCESS_KEY", "rotated-access-key-0123456789-abcdefgh")
    get_settings.cache_clear()
    assert client.get("/api/auth/me").status_code == 401
    old = {"Authorization": f"Bearer {ACCESS_KEY}"}
    assert client.get("/api/providers", headers=old).status_code == 401


def test_unset_key_opens_nothing(anonymous: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ACCESS_KEY", "")
    get_settings.cache_clear()
    assert anonymous.post("/api/auth/login", json={"key": ""}).status_code == 422
    assert anonymous.get("/api/providers", headers={"Authorization": "Bearer "}).status_code == 401


def test_logout_ends_the_session(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


# ── login throttle ───────────────────────────────────────────────────────────


def test_failed_logins_are_throttled_per_ip(database: str) -> None:
    with transaction(database) as db:
        for _ in range(auth.MAX_PER_IP):
            assert auth.login(db, "guess", ip="203.0.113.9") == "invalid"
        assert auth.login(db, ACCESS_KEY, ip="203.0.113.9") == "locked"
        assert isinstance(auth.login(db, ACCESS_KEY, ip="198.51.100.7"), auth.Session)


def test_throttle_answers_429(anonymous: TestClient) -> None:
    for _ in range(auth.MAX_PER_IP):
        anonymous.post("/api/auth/login", json={"key": "guess"})
    assert anonymous.post("/api/auth/login", json={"key": ACCESS_KEY}).status_code == 429


# ── jobs submitted over the API are validated up front ───────────────────────


def test_invalid_job_payload_fails_at_submit(client: TestClient) -> None:
    job = {"prompt_key": "rewrite", "variables": VARS, "model": "m", "extra": 1}
    response = client.post("/api/jobs", json={"kind": "llm.run", "payload": job})
    assert response.status_code == 422


# ── stored provider keys stay with their endpoint ───────────────────────────


@pytest.fixture()
def captured(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, json={"error": {"message": "unauthorised"}})

    original = backends._openai

    def patched(spec: backends.ModelSpec):
        model = original(spec)
        model.client = model.client.with_options(
            http_client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        return model

    monkeypatch.setattr(backends, "_openai", patched)
    return seen


def test_probe_does_not_send_stored_key_to_a_new_url(
    client: TestClient, captured: list[httpx.Request]
) -> None:
    provider = add_provider(client)
    response = client.post(
        "/api/providers/probe",
        json={
            "provider_id": provider["id"],
            "name": "x",
            "kind": "openai",
            "base_url": "https://elsewhere.example/v1",
            "models": ["m"],
        },
    )
    assert response.status_code == 422 and captured == []


def test_probe_with_stored_key_at_saved_url_still_works(
    client: TestClient, captured: list[httpx.Request]
) -> None:
    provider = add_provider(client)
    client.post(
        "/api/providers/probe",
        json={
            "provider_id": provider["id"],
            "name": "x",
            "kind": "openai",
            "base_url": provider["base_url"],
            "models": ["m"],
        },
    )
    assert captured and captured[0].headers["authorization"].endswith("1234567890abcdef")


def test_moving_a_provider_needs_the_key_again(client: TestClient) -> None:
    provider = add_provider(client)
    body = {
        "name": provider["name"],
        "kind": "openai",
        "models": ["gpt-test-mini"],
        "base_url": "https://elsewhere.example/v1",
        "revision": provider["revision"],
    }
    assert client.put(f"/api/providers/{provider['id']}", json=body).status_code == 422
    body["api_key"] = "sk-new-key-0987654321"
    assert client.put(f"/api/providers/{provider['id']}", json=body).status_code == 200


# ── a provider without a key never borrows the host's env key ───────────────

HOST_KEY = "host-env-key-0123456789abcdef"


def keyless(kind: str, **overrides: object) -> backends.ModelSpec:
    values: dict = {
        "kind": kind,
        "protocol": "chat",
        "model": "m",
        "base_url": "",
        "region": "",
        "secret": {},
        "temperature": None,
        "max_tokens": None,
        "timeout": 5.0,
        **overrides,
    }
    return backends.ModelSpec(**values)


def test_keyless_anthropic_is_refused_locally_and_sends_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", HOST_KEY)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", HOST_KEY)
    seen: list[httpx2.Request] = []

    def handle_request(self: httpx2.HTTPTransport, request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(401, json={"type": "error", "error": {"type": "auth"}})

    # Every request the anthropic SDK sends goes through this transport.
    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", handle_request)
    body = {"name": "x", "kind": "anthropic", "base_url": "https://attacker.example"}
    refused = client.post("/api/providers/probe", json={**body, "api_key": ""})
    assert refused.status_code == 200 and refused.json()["ok"] is False
    assert "Enter an API key" in refused.json()["message"]
    with pytest.raises(CallFailed, match="Enter an API key") as failed:
        complete(keyless("anthropic", base_url="https://attacker.example"), "", "hi")
    assert not failed.value.retryable
    assert seen == []

    # A key the user typed is still the one that is sent.
    client.post("/api/providers/probe", json={**body, "api_key": "sk-ant-typed-0123456789"})
    assert len(seen) == 1 and str(seen[0].url).startswith("https://attacker.example/")
    headers = list(seen[0].headers.values())
    assert any("sk-ant-typed-0123456789" in value for value in headers)
    assert all(HOST_KEY not in value for value in headers)


def test_keyless_google_is_refused_before_any_client_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google import genai

    monkeypatch.setenv("GOOGLE_API_KEY", HOST_KEY)
    monkeypatch.setenv("GEMINI_API_KEY", HOST_KEY)
    built: list[dict] = []
    real = genai.Client

    def recording(*args: object, **kwargs: object) -> object:
        built.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(genai, "Client", recording)  # llmfy and backends both build through it
    with pytest.raises(ValueError, match="Enter an API key"):
        backends.build_model(keyless("google"))
    with pytest.raises(ValueError, match="Enter an API key"):
        backends.model_ids(keyless("google"))
    assert built == []

    backends.build_model(keyless("google", secret={"api_key": "AIza-typed-0123456789"}))
    assert built and all(kwargs["api_key"] == "AIza-typed-0123456789" for kwargs in built)


# ── production ───────────────────────────────────────────────────────────────


def production(**overrides: object) -> Settings:
    values = {
        "environment": "production",
        "access_key": secrets.token_urlsafe(32),
        "encryption_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "cookie_secure": True,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize("key", ["", "short-key"])
def test_production_needs_a_strong_access_key(key: str) -> None:
    with pytest.raises(RuntimeError, match="APP_ACCESS_KEY"):
        production(access_key=key).require_safe_runtime()
    production().require_safe_runtime()


def test_docs_are_off_in_production(database: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_ACCESS_KEY", secrets.token_urlsafe(32))
    monkeypatch.setenv(
        "APP_ENCRYPTION_KEY", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    )
    monkeypatch.setenv("APP_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    with TestClient(create_app(database)) as prod:
        assert prod.get("/api/docs").status_code == 404
        assert prod.get("/api/openapi.json").status_code == 404


def test_responses_are_no_store_and_foreign_origins_cannot_write(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    refused = client.post("/api/providers", json={}, headers={"Origin": "https://evil.example"})
    assert refused.status_code == 403 and refused.headers["x-content-type-options"] == "nosniff"
