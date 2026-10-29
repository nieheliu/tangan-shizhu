from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_response_carries_request_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.health_payload", lambda: {"status": "ok", "components": {}}
    )
    response = client.get("/api/v1/health", headers={"X-Request-ID": "req-123"})
    assert response.headers["X-Request-ID"] == "req-123"


def test_request_id_is_generated_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.health_payload", lambda: {"status": "ok", "components": {}}
    )
    response = client.get("/api/v1/health")
    assert response.headers["X-Request-ID"]
