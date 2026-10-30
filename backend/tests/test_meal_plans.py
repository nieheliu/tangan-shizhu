"""加入今日计划。重复加入不新增第二条。"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.session import get_session
from app.main import app
from app.models.entities import MealPlan, Recipe, User
from app.services import auth as auth_service
from app.services.meal_plans import MealPlanError, add_to_plan, delete_plan, list_plans


def test_duplicate_plan_is_not_inserted() -> None:
    day = date(2026, 10, 30)
    existing = MealPlan(
        id=9,
        user_id=1,
        date=day,
        meal_type="午餐",
        recipe_id=2,
    )
    session = MagicMock()
    session.get.return_value = Recipe(id=2, name="燕麦粥")
    session.scalar.return_value = existing
    plan, created = add_to_plan(session, 1, 2, "午餐", plan_date=day)
    assert created is False
    assert plan is existing
    session.add.assert_not_called()


def test_new_plan_is_saved() -> None:
    day = date(2026, 10, 30)
    session = MagicMock()
    session.get.return_value = Recipe(id=2, name="燕麦粥")
    session.scalar.return_value = None
    plan, created = add_to_plan(session, 1, 2, "午餐", plan_date=day)
    assert created is True
    assert plan.user_id == 1
    assert plan.date == day
    assert plan.meal_type == "午餐"
    assert plan.recipe_id == 2
    session.commit.assert_called_once()


def test_unique_conflict_returns_existing_row() -> None:
    day = date(2026, 10, 30)
    existing = MealPlan(id=9, user_id=1, date=day, meal_type="午餐", recipe_id=2)
    session = MagicMock()
    session.get.return_value = Recipe(id=2, name="燕麦粥")
    session.scalar.side_effect = [None, existing]
    session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    plan, created = add_to_plan(session, 1, 2, "午餐", plan_date=day)
    assert created is False
    assert plan is existing
    session.rollback.assert_called_once()


def test_missing_recipe_and_bad_meal() -> None:
    session = MagicMock()
    session.get.return_value = None
    with pytest.raises(MealPlanError) as missing:
        add_to_plan(session, 1, 2, "午餐")
    assert missing.value.code == "recipe_not_found"
    with pytest.raises(MealPlanError) as meal:
        add_to_plan(session, 1, 2, "夜宵")
    assert meal.value.code == "invalid_meal_type"


def test_plans_are_ordered_by_meal_and_delete_checks_owner() -> None:
    day = date(2026, 10, 30)
    dinner = MealPlan(id=1, user_id=1, date=day, meal_type="晚餐", recipe_id=3, servings=Decimal(1))
    breakfast = MealPlan(
        id=2, user_id=1, date=day, meal_type="早餐", recipe_id=1, servings=Decimal(1)
    )
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        (dinner, Recipe(id=3, name="白米饭")),
        (breakfast, Recipe(id=1, name="燕麦粥")),
    ]
    items = list_plans(session, 1, day)
    assert [item["meal_type"] for item in items] == ["早餐", "晚餐"]
    assert items[0]["recipe_name"] == "燕麦粥"

    foreign = MealPlan(id=9, user_id=2, date=day, meal_type="午餐", recipe_id=1, servings=Decimal(1))
    session.get.return_value = foreign
    with pytest.raises(MealPlanError) as caught:
        delete_plan(session, 1, 9)
    assert caught.value.code == "plan_not_found"
    session.delete.assert_not_called()


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


def test_meal_plan_requires_token(client: TestClient) -> None:
    created = client.post(
        "/api/v1/meal-plans",
        json={"recipe_id": 1, "meal_type": "午餐"},
    )
    listed = client.get("/api/v1/meal-plans")
    removed = client.delete("/api/v1/meal-plans/1")
    assert created.status_code == 401
    assert listed.status_code == 401
    assert removed.status_code == 401
    assert created.json()["code"] == "unauthorized"


def test_meal_plan_api_reports_duplicate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = MealPlan(
        id=9,
        user_id=1,
        date=date(2026, 10, 30),
        meal_type="午餐",
        recipe_id=2,
    )
    monkeypatch.setattr(
        "app.api.v1.meal_plans.add_to_plan",
        lambda *_args, **_kwargs: (existing, False),
    )
    token = _token(client)
    response = client.post(
        "/api/v1/meal-plans",
        json={"recipe_id": 2, "meal_type": "午餐"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["already_added"] is True
    assert response.json()["recipe_id"] == 2
