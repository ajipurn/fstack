from fastapi.testclient import TestClient

from app.llm import backends
from tests.conftest import FakeOpenAI, add_provider


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
