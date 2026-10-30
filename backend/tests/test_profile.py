from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.models.entities import HealthProfile, User
from app.services.profile import RECOMMENDATION_FIELDS, recommendation_profile


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    users: dict[int, User] = {}
    profiles: dict[int, HealthProfile] = {}
    monkeypatch.setattr("app.services.nutrition.current_year", lambda: 2026)

    def get_by_username(_session: object, username: str) -> User | None:
        return next((user for user in users.values() if user.username == username), None)

    def get_by_id(_session: object, user_id: int) -> User | None:
        return users.get(user_id)

    def add_user(_session: object, user: User) -> User:
        user.id = len(users) + 1
        users[user.id] = user
        return user

    def get_profile(_session: object, user_id: int) -> HealthProfile | None:
        return profiles.get(user_id)

    def save_profile(_session: object, profile: HealthProfile) -> HealthProfile:
        profile.id = profile.id or len(profiles) + 1
        profiles[profile.user_id] = profile
        return profile

    monkeypatch.setattr("app.services.auth.get_by_username", get_by_username)
    monkeypatch.setattr("app.services.auth.add_user", add_user)
    monkeypatch.setattr("app.api.deps.get_by_id", get_by_id)
    monkeypatch.setattr("app.services.profile.get_by_user_id", get_profile)
    monkeypatch.setattr("app.services.profile.save_profile", save_profile)

    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _token(client: TestClient) -> str:
    created = client.post(
        "/api/v1/auth/register",
        json={"username": "demo", "password": "secret"},
    )
    assert created.status_code == 200
    logged = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "secret"},
    )
    assert logged.status_code == 200
    return str(logged.json()["access_token"])


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "gender": "女",
        "birth_year": 1990,
        "height_cm": 160,
        "weight_kg": 55,
        "activity_level": "中",
        "diseases": ["2型糖尿病"],
        "fasting_glucose": 6.1,
        "hba1c": 6.5,
        "allergies": ["虾"],
        "dislikes": ["香菜"],
        "preferences": {"tastes": ["清淡"], "cuisines": ["家常"]},
    }
    payload.update(overrides)
    return payload


def test_profile_requires_login(client: TestClient) -> None:
    response = client.get("/api/v1/profile")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_empty_profile_and_adult_save(client: TestClient) -> None:
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    empty = client.get("/api/v1/profile", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["birth_year"] is None

    saved = client.put("/api/v1/profile", headers=headers, json=_body())
    assert saved.status_code == 200
    body = saved.json()
    assert body["bmi"] == 21.5
    assert body["suggested_kcal"] == 1650
    assert body["daily_kcal_target"] == 1650
    assert body["kcal_source"] == "待核对"
    assert body["age"] == 36
    assert body["fasting_glucose"] == 6.1
    assert body["recipe_allowed"] is True

    again = client.get("/api/v1/profile", headers=headers)
    assert again.json()["height_cm"] == 160.0
    assert again.json()["allergies"] == ["虾"]


def test_underage_cannot_save(client: TestClient) -> None:
    token = _token(client)
    response = client.put(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {token}"},
        json=_body(birth_year=2010),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "underage"
    stored = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"})
    assert stored.json()["birth_year"] is None


def test_manual_kcal_and_glucose_stay_out_of_recommendation(client: TestClient) -> None:
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    saved = client.put(
        "/api/v1/profile",
        headers=headers,
        json=_body(daily_kcal_target=1800, diseases=["慢性肾病"]),
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["daily_kcal_target"] == 1800
    assert body["suggested_kcal"] == 1650
    assert body["recipe_allowed"] is False
    assert "请就医" in body["recipe_block_message"]

    profile = HealthProfile(
        user_id=1,
        height_cm=160,
        weight_kg=55,
        activity_level="中",
        diseases=["慢性肾病"],
        fasting_glucose=6.1,
        hba1c=6.5,
        allergies=["虾"],
        dislikes=["香菜"],
        preferences={"tastes": ["清淡"], "cuisines": ["家常"]},
        daily_kcal_target=1800,
    )
    inputs = recommendation_profile(profile)
    assert set(inputs) == RECOMMENDATION_FIELDS
    assert "fasting_glucose" not in inputs
    assert "hba1c" not in inputs
    assert inputs["daily_kcal_target"] == 1800
    assert inputs["recipe_allowed"] is False


def test_preview_does_not_require_a_saved_profile(client: TestClient) -> None:
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/v1/profile/preview",
        headers=headers,
        json={"birth_year": 2010, "height_cm": 160, "weight_kg": 55, "activity_level": "中"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["can_save"] is False
    assert body["bmi"] == 21.5
    assert body["suggested_kcal"] == 1650
    stored = client.get("/api/v1/profile", headers=headers)
    assert stored.json()["birth_year"] is None
