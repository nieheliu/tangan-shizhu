"""食谱详情。营养来自食材克数，图谱失败时详情仍返回。"""

from collections.abc import Iterator
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.graph.sync import GraphUnavailable
from app.main import app
from app.models.entities import Food, Recipe, RecipeIngredient, User
from app.services import auth as auth_service
from app.services.recipes import RecipeError, get_recipe_detail


def test_detail_uses_ingredient_numbers_when_graph_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = Recipe(
        id=1,
        name="燕麦粥",
        cuisine="家常",
        meal_types=["早餐"],
        cooking_method="煮",
        steps="燕麦加水煮至软。",
        servings=Decimal(1),
        source="待核对",
    )
    ingredient = RecipeIngredient(
        id=1,
        recipe_id=1,
        food_id=5,
        amount_g=Decimal(100),
        is_main=True,
    )
    food = Food(
        id=5,
        name="燕麦",
        per_g=Decimal(100),
        kcal=Decimal(200),
        carb_g=Decimal(10),
        protein_g=Decimal(1),
        fat_g=Decimal(1),
        fiber_g=Decimal(0),
        sodium_mg=Decimal(0),
        gi=Decimal(50),
        gi_source="待核对",
    )
    session = MagicMock()
    session.get.return_value = recipe
    session.scalars.side_effect = [[ingredient], [food]]
    session.scalar.return_value = None

    def graph_down() -> None:
        raise GraphUnavailable("down")

    monkeypatch.setattr("app.services.recipes.neo4j_driver", graph_down)
    detail = get_recipe_detail(session, 1)
    assert detail["kcal"] == 200.0
    assert detail["gi_band_label"] == "低"
    assert detail["gi_band_source"] == "待核对"
    assert detail["gl_is_approximate"] is True
    assert detail["ingredients"] == [
        {"food_id": 5, "name": "燕麦", "amount_g": 100.0, "is_main": True}
    ]
    assert detail["steps"] == "燕麦加水煮至软。"
    assert detail["graph"] == "down"
    assert detail["links"] == []


def test_missing_recipe_raises() -> None:
    session = MagicMock()
    session.get.return_value = None
    with pytest.raises(RecipeError) as caught:
        get_recipe_detail(session, 9)
    assert caught.value.status_code == 404
    assert caught.value.code == "recipe_not_found"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    users: dict[int, User] = {}

    def get_by_username(_session: object, username: str) -> User | None:
        return next((user for user in users.values() if user.username == username), None)

    def get_by_id(_session: object, user_id: int) -> User | None:
        return users.get(user_id)

    def add_user(_session: object, user: User) -> User:
        user.id = len(users) + 1
        users[user.id] = user
        return user

    monkeypatch.setattr(auth_service, "get_by_username", get_by_username)
    monkeypatch.setattr(auth_service, "add_user", add_user)
    monkeypatch.setattr("app.api.deps.get_by_id", get_by_id)

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


def test_recipe_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/recipes/1")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_recipe_api_returns_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.v1.recipes.get_recipe_detail",
        lambda _session, recipe_id: _detail(recipe_id),
    )
    token = _token(client)
    response = client.get(
        "/api/v1/recipes/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "燕麦粥"
    assert body["kcal"] == 200.0
    assert body["graph"] == "down"


def _detail(recipe_id: int) -> dict[str, object]:
    return {
        "id": recipe_id,
        "name": "燕麦粥",
        "cuisine": "家常",
        "meal_types": ["早餐"],
        "cooking_method": "煮",
        "steps": "燕麦加水煮至软。",
        "servings": 1.0,
        "image_url": None,
        "source": "待核对",
        "ingredients": [{"food_id": 5, "name": "燕麦", "amount_g": 100.0, "is_main": True}],
        "graph": "down",
        "links": [],
        "kcal": 200.0,
        "carb_g": 10.0,
        "protein_g": 1.0,
        "fat_g": 1.0,
        "fiber_g": 0.0,
        "sodium_mg": 0.0,
        "oil_estimated": False,
        "main_staple_gi": 50.0,
        "gi_band": "low",
        "gi_band_label": "低",
        "gi_band_source": "待核对",
        "gl_estimate": 5.0,
        "gl_is_approximate": True,
    }
