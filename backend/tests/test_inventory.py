from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.models.entities import Food, FoodUnitConversion, InventoryItem, User
from app.services.inventory import (
    expiry_status,
    run_expiry_check,
    start_expiry_scheduler,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    users: dict[int, User] = {}
    foods = {
        1: Food(id=1, name="番茄", category="蔬菜"),
    }
    conversions = {
        (1, "克"): FoodUnitConversion(food_id=1, unit="克", grams_per_unit=Decimal(1)),
    }
    items: dict[int, InventoryItem] = {}
    monkeypatch.setattr(
        "app.services.inventory.today_in_app_tz", lambda: date(2026, 10, 30)
    )

    def get_by_username(_session: object, username: str) -> User | None:
        return next((user for user in users.values() if user.username == username), None)

    def get_by_id(_session: object, user_id: int) -> User | None:
        return users.get(user_id)

    def add_user(_session: object, user: User) -> User:
        user.id = len(users) + 1
        users[user.id] = user
        return user

    def search(_session: object, keyword: str, limit: int) -> list[Food]:
        text = keyword.strip()
        matched = [food for food in foods.values() if text and text in food.name]
        return matched[:limit]

    def factors(_session: object, food_ids: list[int]) -> dict[tuple[int, str], FoodUnitConversion]:
        return {
            key: value
            for key, value in conversions.items()
            if key[0] in food_ids
        }

    def food_by_id(_session: object, food_id: int) -> Food | None:
        return foods.get(food_id)

    def conversion(_session: object, food_id: int, unit: str) -> FoodUnitConversion | None:
        return conversions.get((food_id, unit))

    def listed(_session: object, user_id: int) -> list[tuple[InventoryItem, Food]]:
        return [
            (item, foods[item.food_id])
            for item in items.values()
            if item.user_id == user_id
        ]

    def due(
        _session: object, user_id: int, today: date
    ) -> list[tuple[InventoryItem, Food]]:
        return [
            (item, foods[item.food_id])
            for item in items.values()
            if item.user_id == user_id
            and item.expires_at is not None
            and expiry_status(item.expires_at, today) in {"expiring", "expired"}
        ]

    def one_item(_session: object, user_id: int, item_id: int) -> InventoryItem | None:
        item = items.get(item_id)
        if item is None or item.user_id != user_id:
            return None
        return item

    def save(_session: object, item: InventoryItem) -> InventoryItem:
        if item.id is None:
            item.id = max(items, default=0) + 1
        items[item.id] = item
        return item

    def remove(_session: object, item: InventoryItem) -> None:
        items.pop(item.id, None)

    monkeypatch.setattr("app.services.auth.get_by_username", get_by_username)
    monkeypatch.setattr("app.services.auth.add_user", add_user)
    monkeypatch.setattr("app.api.deps.get_by_id", get_by_id)
    monkeypatch.setattr("app.services.inventory.search_foods", search)
    monkeypatch.setattr("app.services.inventory.conversions_for", factors)
    monkeypatch.setattr("app.services.inventory.get_food", food_by_id)
    monkeypatch.setattr("app.services.inventory.get_conversion", conversion)
    monkeypatch.setattr("app.services.inventory.list_items", listed)
    monkeypatch.setattr("app.services.inventory.list_due", due)
    monkeypatch.setattr("app.services.inventory.get_item", one_item)
    monkeypatch.setattr("app.services.inventory.save_item", save)
    monkeypatch.setattr("app.services.inventory.delete_item", remove)

    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _token(client: TestClient) -> str:
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"username": "demo", "password": "secret"},
        ).status_code
        == 200
    )
    logged = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "secret"},
    )
    assert logged.status_code == 200
    return str(logged.json()["access_token"])


def test_expiry_window() -> None:
    today = date(2026, 10, 30)
    assert expiry_status(None, today) == "unknown"
    assert expiry_status(date(2026, 10, 29), today) == "expired"
    assert expiry_status(date(2026, 10, 30), today) == "expiring"
    assert expiry_status(date(2026, 11, 1), today) == "expiring"
    assert expiry_status(date(2026, 11, 2), today) == "ok"


def test_scheduler_stays_off_during_tests() -> None:
    start_expiry_scheduler()
    assert os_scheduler_off()


def os_scheduler_off() -> bool:
    from app.services.inventory import _scheduler

    return _scheduler is None


def test_expiry_check_counts_due_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Session:
        def __enter__(self) -> MagicMock:
            return MagicMock()

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr("app.services.inventory.get_sessionmaker", lambda: _Session)
    monkeypatch.setattr("app.services.inventory.count_due", lambda _session, _today: 2)
    monkeypatch.setattr(
        "app.services.inventory.today_in_app_tz", lambda: date(2026, 10, 30)
    )
    assert run_expiry_check() == 2


def test_unknown_unit_is_rejected_and_grams_use_the_table(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_token(client)}"}
    found = client.get("/api/v1/foods/search", headers=headers, params={"q": "番"})
    assert found.status_code == 200
    assert found.json()[0]["name"] == "番茄"
    assert found.json()[0]["units"] == ["克"]

    rejected = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"food_id": 1, "quantity": 2, "unit": "个", "expires_at": "2026-10-31"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "unknown_unit"
    assert client.get("/api/v1/inventory", headers=headers).json() == []

    saved = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"food_id": 1, "quantity": 200, "unit": "克", "expires_at": "2026-10-31"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["grams"] == 200.0
    assert body["status"] == "expiring"

    expired = client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"food_id": 1, "quantity": 1, "unit": "克", "expires_at": "2026-10-28"},
    )
    assert expired.json()["status"] == "expired"
    reminders = client.get("/api/v1/inventory/reminders", headers=headers)
    assert {row["status"] for row in reminders.json()} == {"expiring", "expired"}

    removed = client.delete(f"/api/v1/inventory/{body['id']}", headers=headers)
    assert removed.status_code == 200
    missing = client.delete("/api/v1/inventory/999", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
