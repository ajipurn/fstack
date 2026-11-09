from fastapi.testclient import TestClient

from app.db.session import Connection


def test_a_write_commits_before_its_response_is_sent(client: TestClient, monkeypatch) -> None:
    """A client that refetches as soon as a write answers must see the new rows."""
    events: list[str] = []
    commit = Connection.commit

    def recording_commit(self: Connection) -> None:
        commit(self)
        events.append("commit")

    monkeypatch.setattr(Connection, "commit", recording_commit)
    app = client.app

    async def recording_app(scope, receive, send):
        async def recording_send(message):
            if message["type"] == "http.response.start":
                events.append("response")
            await send(message)

        await app(scope, receive, recording_send)

    with TestClient(recording_app, headers=client.headers, cookies=client.cookies) as recorder:
        body = {"name": "OpenAI", "kind": "openai", "api_key": "sk-test-1234567890abcdef"}
        assert recorder.post("/api/providers", json=body).status_code == 201
    assert events[-2:] == ["commit", "response"]
