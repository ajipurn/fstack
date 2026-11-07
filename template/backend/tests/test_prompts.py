from fastapi.testclient import TestClient


def test_file_seed_creates_active_v1(client: TestClient) -> None:
    prompt = client.get("/api/prompts/summarize").json()
    active = next(v for v in prompt["versions"] if v["id"] == prompt["active_version_id"])
    assert active["version"] == 1 and active["status"] == "published"
    assert active["variables"] == ["audience", "text"]
    assert len(active["digest"]) == 64


def test_draft_publish_activate_rollback(client: TestClient) -> None:
    draft = client.post("/api/prompts/rewrite/draft", json={}).json()
    assert draft["versions"][0]["status"] == "draft"
    assert client.post("/api/prompts/rewrite/draft", json={}).status_code == 409  # one draft

    saved = client.put(
        "/api/prompts/rewrite/draft",
        json={"system": "Be terse.", "user_template": "{{tone}}: {{text}}", "revision": 1},
    )
    assert saved.status_code == 200, saved.text
    stale = client.put(
        "/api/prompts/rewrite/draft",
        json={"system": "x", "user_template": "{{text}}", "revision": 1},
    )
    assert stale.status_code == 409  # optimistic lock

    published = client.post(
        "/api/prompts/rewrite/draft/publish", json={"revision": 2, "note": "terser"}
    ).json()
    v2 = published["versions"][0]
    assert v2["version"] == 2 and published["active_version_id"] == v2["id"]

    v1 = published["versions"][1]
    rolled = client.post("/api/prompts/rewrite/activate", json={"version_id": v1["id"]}).json()
    assert rolled["active_version_id"] == v1["id"]


def test_publishing_identical_content_is_rejected(client: TestClient) -> None:
    client.post("/api/prompts/rewrite/draft", json={})
    response = client.post("/api/prompts/rewrite/draft/publish", json={"revision": 1})
    assert response.status_code == 409
    assert "Identical to v1" in response.json()["detail"]


def test_bad_placeholders_are_rejected(client: TestClient) -> None:
    client.post("/api/prompts/rewrite/draft", json={})
    response = client.put(
        "/api/prompts/rewrite/draft",
        json={"system": "{{ Bad Name }}", "user_template": "{{text}}", "revision": 1},
    )
    assert response.status_code == 422
