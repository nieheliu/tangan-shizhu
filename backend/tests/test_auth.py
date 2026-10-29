from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.models.entities import User
from app.services import auth as auth_service


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    users: dict[int, User] = {}

    def get_by_username(_session: object, username: str) -> User | None:
        return next(
            (user for user in users.values() if user.username == username), None
        )

    def get_by_id(_session: object, user_id: int) -> User | None:
        return users.get(user_id)

    def add_user(_session: object, user: User) -> User:
        user.id = len(users) + 1
        users[user.id] = user
        return user

    monkeypatch.setattr("app.services.auth.get_by_username", get_by_username)
    monkeypatch.setattr("app.services.auth.add_user", add_user)
    monkeypatch.setattr("app.api.deps.get_by_id", get_by_id)
    monkeypatch.setattr("app.api.v1.admin.count_users", lambda _session: len(users))

    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _register(
    client: TestClient, username: str = "demo", password: str = "secret"
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def _login(client: TestClient, username: str = "demo", password: str = "secret") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


def test_register_and_login(client: TestClient) -> None:
    created = client.post(
        "/api/v1/auth/register",
        json={"username": "demo", "password": "secret"},
    )
    assert created.status_code == 200
    assert created.json() == {"id": 1, "username": "demo", "role": "user"}
    assert created.headers["X-Request-ID"]

    token = _login(client)
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "demo"


def test_duplicate_username_is_rejected(client: TestClient) -> None:
    _register(client)
    again = client.post(
        "/api/v1/auth/register",
        json={"username": "demo", "password": "another"},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "username_taken"


def test_login_rejects_wrong_password(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_missing_token_is_unauthorized(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["detail"] == "未登录"
    assert body["code"] == "unauthorized"


def test_user_cannot_open_admin_stats(client: TestClient) -> None:
    _register(client)
    token = _login(client)
    response = client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "需要管理员权限", "code": "forbidden"}


def test_admin_can_open_stats(client: TestClient) -> None:
    _register(client, username="admin-user")
    user = auth_service.get_by_username(object(), "admin-user")
    assert user is not None
    user.role = "admin"
    token = _login(client, username="admin-user")
    response = client.get(
        "/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == {"users": 1}
