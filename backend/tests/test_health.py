from fastapi.testclient import TestClient

from app.core import health as health_core
from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_health_lists_components_when_dependencies_are_down(monkeypatch) -> None:
    for name in ("check_postgres", "check_neo4j", "check_chroma", "check_llm"):
        monkeypatch.setattr(health_core, name, lambda: "down")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["components"] == {
        "postgresql": "down",
        "neo4j": "down",
        "chroma": "down",
        "llm": "down",
    }


def test_health_turns_checker_errors_into_down(monkeypatch) -> None:
    def explode() -> str:
        raise RuntimeError("unreachable")

    for name in ("check_postgres", "check_neo4j", "check_chroma", "check_llm"):
        monkeypatch.setattr(health_core, name, explode)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert set(response.json()["components"].values()) == {"down"}


def test_unconfigured_remote_services_are_down() -> None:
    blank = Settings(
        database_url="",
        neo4j_uri="",
        neo4j_password="",
        llm_api_key="",
    )
    health_core.get_settings.cache_clear()
    original = health_core.get_settings
    health_core.get_settings = lambda: blank
    try:
        assert health_core.check_postgres() == "down"
        assert health_core.check_neo4j() == "down"
        assert health_core.check_llm() == "down"
    finally:
        health_core.get_settings = original
        health_core.get_settings.cache_clear()


def test_docs_available() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
