"""购物清单。库存和过敏原在生成时处理，克数不凭空补。"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.services.shopping import (
    ShoppingError,
    _stock_grams,
    build_purchase,
    choose_unit,
    move_checked_to_inventory,
    scale_grams,
    update_item,
)


def _need(food_id: int, name: str, grams: str, **extra: object) -> dict[str, object]:
    item: dict[str, object] = {
        "food_id": food_id,
        "name": name,
        "category": "蔬菜",
        "alias": (),
        "grams": Decimal(grams),
    }
    item.update(extra)
    return item


def test_purchase_subtracts_stock_and_skips_covered_foods() -> None:
    purchases, excluded = build_purchase(
        [_need(1, "番茄", "200"), _need(2, "鸡蛋", "50")],
        {1: Decimal(200)},
        [],
        {},
    )
    assert excluded == []
    assert [(item["name"], item["amount_g"]) for item in purchases] == [
        ("鸡蛋", Decimal("50.00")),
    ]


def test_needs_add_before_stock_is_subtracted() -> None:
    purchases, _excluded = build_purchase(
        [_need(1, "荞麦", "60", category="主食"), _need(1, "荞麦", "60", category="主食")],
        {1: Decimal(20)},
        [],
        {1: {"克": Decimal(1), "碗": Decimal(50)}},
    )
    assert len(purchases) == 1
    assert purchases[0]["amount_g"] == Decimal("100.00")
    assert purchases[0]["quantity"] == Decimal(2)
    assert purchases[0]["unit"] == "碗"


def test_allergen_is_left_off_the_list() -> None:
    purchases, excluded = build_purchase(
        [_need(3, "虾仁", "80", alias=("海虾",))],
        {},
        ["虾"],
        {},
    )
    assert purchases == []
    assert excluded == [{"food_id": 3, "food_name": "虾仁", "reason": "过敏原"}]


def test_odd_grams_stay_in_grams() -> None:
    quantity, unit = choose_unit(Decimal(180), {"个": Decimal(50), "克": Decimal(1)})
    assert (quantity, unit) == (Decimal(180), "克")


def test_expired_and_unknown_units_are_not_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date(2026, 10, 30)
    expired = SimpleNamespace(
        food_id=1, quantity=Decimal(100), unit="克", expires_at=date(2026, 10, 1)
    )
    unknown = SimpleNamespace(food_id=2, quantity=Decimal(30), unit="把", expires_at=None)
    held = SimpleNamespace(food_id=3, quantity=Decimal(2), unit="个", expires_at=None)
    monkeypatch.setattr(
        "app.services.shopping.list_items",
        lambda *_args: [
            (expired, SimpleNamespace()),
            (unknown, SimpleNamespace()),
            (held, SimpleNamespace()),
        ],
    )
    monkeypatch.setattr(
        "app.services.shopping.conversions_for",
        lambda *_args: {(3, "个"): SimpleNamespace(grams_per_unit=Decimal(50))},
    )
    assert _stock_grams(MagicMock(), 1, today) == {3: Decimal(100)}
    assert scale_grams(Decimal(100), Decimal(2), Decimal(1)) == Decimal(50)
    assert scale_grams(Decimal(60), Decimal(1), Decimal(2)) == Decimal(120)
    assert scale_grams(None, Decimal(1), Decimal(1)) is None


def test_other_users_item_is_hidden() -> None:
    item = SimpleNamespace(
        id=4, shopping_list_id=9, food_id=1, amount_g=Decimal(10), checked=False
    )
    shopping = SimpleNamespace(id=9, user_id=2)
    session = MagicMock()
    session.get.side_effect = lambda _model, key: item if key == 4 else shopping
    with pytest.raises(ShoppingError) as caught:
        update_item(session, 1, 4, checked=True, amount_g=None)
    assert caught.value.code == "item_not_found"
    session.commit.assert_not_called()


def test_unchecked_list_is_not_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    shopping = SimpleNamespace(id=3, user_id=1)
    monkeypatch.setattr("app.services.shopping._owned_list", lambda *_args: shopping)
    monkeypatch.setattr(
        "app.services.shopping._item_rows",
        lambda *_args: [(SimpleNamespace(checked=False), SimpleNamespace(name="荞麦"))],
    )
    with pytest.raises(ShoppingError) as caught:
        move_checked_to_inventory(MagicMock(), 1, 3)
    assert caught.value.code == "nothing_checked"


@pytest.fixture
def client() -> Iterator[TestClient]:
    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_shopping_requires_token(client: TestClient) -> None:
    created = client.post("/api/v1/shopping/generate", json={"scope": "daily"})
    listed = client.get("/api/v1/shopping/1")
    patched = client.patch("/api/v1/shopping/items/1", json={"checked": True})
    moved = client.post("/api/v1/shopping/1/to-inventory")
    assert created.status_code == 401
    assert listed.status_code == 401
    assert patched.status_code == 401
    assert moved.status_code == 401
    assert created.json()["code"] == "unauthorized"
