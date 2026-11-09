import json

from fastapi.testclient import TestClient

from app.db.session import transaction
from app.schemas.models import RunPrompt
from app.services import pricing, runs
from app.workers import worker
from tests.conftest import MODELS_DEV, FakeOpenAI, add_provider

SUMMARY = {
    "title": "Quarterly results",
    "summary": "Revenue grew. Costs fell.",
    "key_points": ["Revenue +12%", "Costs -3%", "Hiring paused"],
    "sentiment": "positive",
}


def run(client: TestClient, provider_id: str, prompt: str, variables: dict, **extra):
    body = {
        "prompt_key": prompt,
        "variables": variables,
        "provider_id": provider_id,
        "model": "gpt-test-mini",
        **extra,
    }
    return client.post("/api/runs", json=body)


def test_provider_secret_is_never_returned(client: TestClient) -> None:
    provider = add_provider(client)
    assert "encrypted_secret" not in provider and "api_key" not in provider
    assert provider["secret_configured"] and provider["secret_hint"] == "sk-••••cdef"


def test_structured_prompt_end_to_end(
    client: TestClient, database: str, fake_openai: FakeOpenAI
) -> None:
    with transaction(database) as db:
        pricing.sync_catalog(db, MODELS_DEV)
    provider = add_provider(client)
    fake_openai.replies = ["```json\n" + json.dumps(SUMMARY) + "\n```"]

    response = run(
        client,
        provider["id"],
        "summarize",
        {"text": "Q3 report…", "audience": "the board"},
        max_tokens=1000,
        temperature=0.2,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["data"] == SUMMARY and result["prompt"] == "summarize"
    assert result["prompt_version"] == 1
    assert result["usage"]["input_tokens"] == 1200
    assert result["cost_usd"] == (1200 * 0.25 + 300 * 2.0) / 1_000_000

    sent = fake_openai.requests[0]
    assert sent["model"] == "gpt-test-mini" and sent["max_tokens"] == 1000
    assert sent["temperature"] == 0.2
    assert "JSON Schema" in sent["messages"][0]["content"]
    assert "the board" in sent["messages"][1]["content"]

    calls = client.get("/api/usage/calls?prompt=summarize").json()
    assert calls[0]["status"] == "ok" and calls[0]["prompt_version"] == 1
    summary = client.get("/api/usage/summary?days=7").json()
    assert summary["totals"]["calls"] == 1
    assert summary["by_prompt"][0]["prompt_key"] == "summarize"
    assert len(summary["by_day"]) == 7


def test_unset_temperature_and_max_tokens_use_the_models_defaults(
    client: TestClient, fake_openai: FakeOpenAI
) -> None:
    provider = add_provider(client)
    assert run(client, provider["id"], "rewrite", {"text": "hi", "tone": "warm"}).status_code == 200
    sent = fake_openai.requests[0]
    assert "temperature" not in sent and "max_tokens" not in sent and "top_p" not in sent


def test_anthropic_gets_the_models_output_limit(client: TestClient, database: str) -> None:
    with transaction(database) as db:
        pricing.sync_catalog(db, MODELS_DEV)
    provider = add_provider(
        client, name="Claude", kind="anthropic", base_url="", catalog_id="anthropic"
    )
    body = RunPrompt(prompt_key="rewrite", provider_id="Claude", model="claude-test")
    with transaction(database) as db:
        assert runs.resolve(db, body).model_spec.max_tokens == 64000  # models.dev limit.output
        unknown = body.model_copy(update={"model": "claude-unlisted"})
        assert runs.resolve(db, unknown).model_spec.max_tokens == runs.ANTHROPIC_MAX_TOKENS
        chosen = body.model_copy(update={"max_tokens": 900})
        assert runs.resolve(db, chosen).model_spec.max_tokens == 900
    assert provider["kind"] == "anthropic"


def test_code_can_name_the_provider(
    client: TestClient, database: str, fake_openai: FakeOpenAI
) -> None:
    add_provider(client)
    result = runs.run_prompt(
        "rewrite", {"text": "hi", "tone": "calm"}, provider="OpenAI", model="gpt-test-mini"
    )
    assert result.text == "OK" and result.provider == "OpenAI"


def test_invalid_json_gets_one_correction(client: TestClient, fake_openai: FakeOpenAI) -> None:
    provider = add_provider(client)
    fake_openai.replies = ['{"title": 1}', json.dumps(SUMMARY)]
    result = run(client, provider["id"], "summarize", {"text": "x", "audience": "y"}).json()
    assert result["attempts"] == 2 and result["data"]["sentiment"] == "positive"
    assert "previous answer was rejected" in fake_openai.requests[1]["messages"][0]["content"]
    statuses = [c["status"] for c in client.get("/api/usage/calls").json()]
    assert statuses == ["ok", "error"]  # newest first; the failed attempt is still recorded


def test_unpriced_model_records_null_cost(client: TestClient, fake_openai: FakeOpenAI) -> None:
    provider = add_provider(client, models=["mystery-model"])
    result = run(
        client, provider["id"], "rewrite", {"text": "hi", "tone": "warm"}, model="mystery-model"
    ).json()
    assert result["cost_usd"] is None
    assert client.get("/api/usage/summary").json()["totals"]["unpriced_calls"] == 1


def test_missing_variables_and_unknown_prompt(client: TestClient) -> None:
    provider = add_provider(client)
    response = run(client, provider["id"], "rewrite", {})
    assert response.status_code == 422 and "Missing variables" in response.json()["detail"]
    assert run(client, provider["id"], "nope", {}).status_code == 404
    assert run(client, "no-such-provider", "rewrite", {}).status_code == 404


def test_a_run_can_use_a_draft(client: TestClient, fake_openai: FakeOpenAI) -> None:
    provider = add_provider(client)
    client.post("/api/prompts/rewrite/draft", json={})
    draft = client.put(
        "/api/prompts/rewrite/draft",
        json={"system": "DRAFT SYSTEM", "user_template": "{{text}}", "revision": 1},
    ).json()
    result = run(
        client, provider["id"], "rewrite", {"text": "hi"}, prompt_version_id=draft["id"]
    ).json()
    assert result["prompt_version"] == 2
    assert fake_openai.requests[0]["messages"][0]["content"] == "DRAFT SYSTEM"


def test_job_runs_in_worker(client: TestClient, database: str, fake_openai: FakeOpenAI) -> None:
    provider = add_provider(client)
    payload = {
        "prompt_key": "rewrite",
        "variables": {"text": "hi", "tone": "calm"},
        "provider_id": provider["id"],
        "model": "gpt-test-mini",
    }
    job = client.post("/api/jobs", json={"kind": "llm.run", "payload": payload}).json()
    assert job["status"] == "queued"
    assert worker.process_one(database) is True
    done = client.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "succeeded" and done["result"]["text"] == "OK"
    assert worker.process_one(database) is False


def test_session_writes_need_csrf(client: TestClient) -> None:
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/providers", json={}).status_code == 403


# ── retry and stop ───────────────────────────────────────────────────────────


def test_rate_limits_are_retried_with_backoff(
    client: TestClient, fake_openai: FakeOpenAI, monkeypatch
) -> None:
    monkeypatch.setattr(runs, "BACKOFF_SECONDS", (0, 0, 0, 0, 0))
    provider = add_provider(client)
    fake_openai.failures = [429, 503]
    result = run(client, provider["id"], "rewrite", {"text": "hi", "tone": "calm"}).json()
    assert result["text"] == "OK" and result["attempts"] == 3
    statuses = [c["status"] for c in client.get("/api/usage/calls").json()]
    assert statuses == ["ok", "error", "error"]  # every attempt is on record


def test_failures_the_provider_may_have_processed_are_not_retried(
    client: TestClient, fake_openai: FakeOpenAI, monkeypatch
) -> None:
    monkeypatch.setattr(runs, "BACKOFF_SECONDS", (0, 0, 0, 0, 0))
    provider = add_provider(client)
    fake_openai.failures = [401]
    response = run(client, provider["id"], "rewrite", {"text": "hi", "tone": "calm"})
    assert response.status_code == 502 and len(fake_openai.requests) == 1
    fake_openai.failures = [429]
    response = run(client, provider["id"], "rewrite", {"text": "hi", "tone": "calm"}, retries=0)
    assert response.status_code == 502 and len(fake_openai.requests) == 2


def test_timeouts_are_never_retryable() -> None:
    import llmfy

    from app.llm.errors import retryable

    assert retryable(llmfy.RateLimitException("slow down"))
    assert retryable(llmfy.ServiceUnavailableException("overloaded"))
    assert not retryable(llmfy.TimeoutException("took too long"))
    assert not retryable(llmfy.QuotaExceededException("out of credit"))


def test_stop_ends_a_run_before_its_next_attempt(
    client: TestClient, fake_openai: FakeOpenAI, monkeypatch
) -> None:
    import pytest

    from app.core.exceptions import Cancelled

    monkeypatch.setattr(runs, "BACKOFF_SECONDS", (30, 30, 30, 30, 30))
    add_provider(client)
    fake_openai.failures = [429, 429]
    with pytest.raises(Cancelled):
        runs.run_prompt(
            "rewrite",
            {"text": "hi", "tone": "calm"},
            provider="OpenAI",
            model="gpt-test-mini",
            stop=lambda: len(fake_openai.requests) >= 1,  # stop after the first try
        )
    assert len(fake_openai.requests) == 1  # no retry started, no 30s wait either


def test_jobs_can_be_cancelled_while_running_and_retried(client: TestClient, database: str) -> None:
    from app.services import jobs

    provider = add_provider(client)
    payload = {
        "prompt_key": "rewrite",
        "variables": {"text": "hi", "tone": "calm"},
        "provider_id": provider["id"],
        "model": "gpt-test-mini",
    }
    job = client.post("/api/jobs", json={"kind": "llm.run", "payload": payload}).json()
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 409  # still queued
    with transaction(database) as db:
        claimed, token = jobs.claim(db)  # a worker picks it up
    assert claimed["id"] == job["id"]

    cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    with transaction(database) as db:
        assert jobs.heartbeat(db, job["id"], token) is False  # the worker sees it's lost
        assert jobs.finish(db, job["id"], token, result={"text": "late"}) is False

    again = client.post(f"/api/jobs/{job['id']}/retry").json()
    assert again["status"] == "queued" and again["id"] != job["id"]
    assert again["payload"] == payload


# ── housekeeping ─────────────────────────────────────────────────────────────


def test_deleting_a_prompt_keeps_its_call_history(
    client: TestClient, fake_openai: FakeOpenAI
) -> None:
    provider = add_provider(client)
    run(client, provider["id"], "rewrite", {"text": "hi", "tone": "calm"})
    assert client.delete("/api/prompts/rewrite").status_code == 204
    assert client.get("/api/prompts/rewrite").status_code == 404
    assert [p["key"] for p in client.get("/api/prompts").json()] == ["summarize"]
    assert client.get("/api/usage/calls").json()[0]["prompt_key"] == "rewrite"
    assert client.delete("/api/prompts/rewrite").status_code == 404


def test_clearing_usage_deletes_every_call(client: TestClient, fake_openai: FakeOpenAI) -> None:
    provider = add_provider(client)
    run(client, provider["id"], "rewrite", {"text": "hi", "tone": "calm"})
    run(client, provider["id"], "rewrite", {"text": "hi", "tone": "warm"})
    assert client.delete("/api/usage/calls").json() == {"deleted": 2}
    assert client.get("/api/usage/calls").json() == []
    assert client.get("/api/usage/summary").json()["totals"]["calls"] == 0
