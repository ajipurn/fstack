from fastapi.testclient import TestClient

from app.db.session import transaction
from app.services import audit


def test_settings_start_at_their_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {"nav_position": "top"}


def test_nav_position_is_saved_for_the_workspace(client: TestClient, database: str) -> None:
    response = client.put("/api/settings", json={"nav_position": "side"})
    assert response.status_code == 200, response.text
    assert response.json() == {"nav_position": "side"}
    assert client.get("/api/settings").json() == {"nav_position": "side"}

    # Saved again (an update, not a second row), and a no-op is not audited.
    assert client.put("/api/settings", json={"nav_position": "top"}).json() == {
        "nav_position": "top"
    }
    assert client.put("/api/settings", json={"nav_position": "top"}).status_code == 200
    with transaction(database, write=False) as db:
        rows = db.execute("SELECT `key`, updated_by FROM fstack_settings").fetchall()
        events = audit.recent(db, "setting:nav_position")
    assert [(r["key"], r["updated_by"]) for r in rows] == [("nav_position", "dashboard")]
    assert [e["action"] for e in events] == ["setting.updated", "setting.updated"]


def test_an_empty_update_changes_nothing(client: TestClient) -> None:
    assert client.put("/api/settings", json={}).json() == {"nav_position": "top"}


def test_unknown_values_and_fields_are_refused(client: TestClient) -> None:
    assert client.put("/api/settings", json={"nav_position": "bottom"}).status_code == 422
    assert client.put("/api/settings", json={"color": "red"}).status_code == 422


def test_settings_need_a_session(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/settings").status_code == 401
