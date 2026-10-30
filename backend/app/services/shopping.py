"""购物清单。所需克数减去未过期库存，过敏原不进入清单。"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Food,
    MealPlan,
    Recipe,
    RecipeIngredient,
    ShoppingItem,
    ShoppingList,
)
from app.repositories.inventory import (
    conversions_for,
    get_conversion,
    get_food,
    list_items,
)
from app.repositories.profiles import get_by_user_id
from app.schemas.inventory import InventoryWrite
from app.services.inventory import (
    InventoryError,
    create_item,
    expiry_status,
    today_in_app_tz,
)

_QUANTUM = Decimal("0.01")
_UNCATEGORIZED = "未分类"


class ShoppingError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def generate_list(
    session: Session,
    user_id: int,
    *,
    scope: str,
    day: date | None = None,
) -> dict[str, object]:
    if scope not in {"daily", "weekly"}:
        raise ShoppingError(status_code=422, detail="范围不正确", code="invalid_scope")
    end = day or today_in_app_tz()
    start = end if scope == "daily" else end - timedelta(days=6)
    needs = _planned_needs(session, user_id, start, end)
    stock = _stock_grams(session, user_id, end)
    purchases, excluded = build_purchase(
        needs,
        stock,
        _allergies(session, user_id),
        _conversion_map(session, [item["food_id"] for item in needs]),
    )
    shopping = ShoppingList(user_id=user_id)
    session.add(shopping)
    session.flush()
    for item in purchases:
        session.add(
            ShoppingItem(
                shopping_list_id=shopping.id,
                food_id=int(item["food_id"]),
                amount_g=item["amount_g"],
                checked=False,
            )
        )
    session.commit()
    session.refresh(shopping)
    return _payload(session, shopping, start, end, excluded)


def get_list(session: Session, user_id: int, list_id: int) -> dict[str, object]:
    shopping = _owned_list(session, user_id, list_id)
    today = today_in_app_tz()
    return _payload(session, shopping, today, today, [])


def add_manual_item(
    session: Session,
    user_id: int,
    list_id: int,
    food_id: int,
    amount_g: Decimal,
) -> dict[str, object]:
    shopping = _owned_list(session, user_id, list_id)
    food = get_food(session, food_id)
    if food is None:
        raise ShoppingError(status_code=404, detail="找不到这种食材", code="food_not_found")
    names = tuple(str(name) for name in food.alias or [])
    if _is_allergen(food.name, names, _allergies(session, user_id)):
        raise ShoppingError(
            status_code=422,
            detail="这种食材在过敏原里，不能放进清单",
            code="allergen_blocked",
        )
    existing = session.scalars(
        select(ShoppingItem).where(
            ShoppingItem.shopping_list_id == shopping.id,
            ShoppingItem.food_id == food_id,
        )
    ).one_or_none()
    if existing is None:
        session.add(
            ShoppingItem(
                shopping_list_id=shopping.id,
                food_id=food_id,
                amount_g=_quantize(amount_g),
                checked=False,
            )
        )
    else:
        existing.amount_g = _quantize(existing.amount_g + amount_g)
    session.commit()
    today = today_in_app_tz()
    return _payload(session, shopping, today, today, [])


def update_item(
    session: Session,
    user_id: int,
    item_id: int,
    *,
    checked: bool | None,
    amount_g: Decimal | None,
) -> dict[str, object]:
    item = session.get(ShoppingItem, item_id)
    shopping = None if item is None else session.get(ShoppingList, item.shopping_list_id)
    if item is None or shopping is None or shopping.user_id != user_id:
        raise ShoppingError(status_code=404, detail="找不到这条清单", code="item_not_found")
    if checked is not None:
        item.checked = checked
    if amount_g is not None:
        item.amount_g = _quantize(amount_g)
    session.commit()
    food = get_food(session, item.food_id)
    conversions = _conversion_map(session, [item.food_id]).get(item.food_id, {})
    return _item_view(item, food, conversions)


def move_checked_to_inventory(
    session: Session, user_id: int, list_id: int
) -> dict[str, object]:
    shopping = _owned_list(session, user_id, list_id)
    rows = _item_rows(session, shopping.id)
    checked = [(item, food) for item, food in rows if item.checked]
    if not checked:
        raise ShoppingError(status_code=422, detail="还没有勾选已购买的食材", code="nothing_checked")
    added: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    purchased = today_in_app_tz()
    for item, food in checked:
        conversion = get_conversion(session, item.food_id, "克")
        if conversion is None or conversion.grams_per_unit <= 0:
            skipped.append({"food_name": food.name, "detail": "没有「克」的换算，没有入库"})
            continue
        quantity = _quantize(item.amount_g / conversion.grams_per_unit)
        try:
            saved = create_item(
                session,
                user_id,
                InventoryWrite(
                    food_id=item.food_id,
                    quantity=quantity,
                    unit="克",
                    purchased_at=purchased,
                    expires_at=None,
                ),
            )
        except InventoryError as exc:
            skipped.append({"food_name": food.name, "detail": exc.detail})
            continue
        session.delete(item)
        added.append(
            {
                "id": saved.id,
                "food_id": saved.food_id,
                "food_name": saved.food_name,
                "quantity": saved.quantity,
                "unit": saved.unit,
                "grams": saved.grams,
            }
        )
    session.commit()
    today = today_in_app_tz()
    return {
        "added": added,
        "skipped": skipped,
        "shopping": _payload(session, shopping, today, today, []),
    }


def build_purchase(
    needs: list[dict[str, object]],
    stock: dict[int, Decimal],
    allergies: list[str],
    conversions: dict[int, dict[str, Decimal]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    totals: dict[int, dict[str, object]] = {}
    for need in needs:
        food_id = int(need["food_id"])
        grams = need["grams"]
        if not isinstance(grams, Decimal):
            continue
        current = totals.get(food_id)
        if current is None:
            totals[food_id] = {
                "food_id": food_id,
                "name": str(need["name"]),
                "category": need.get("category"),
                "alias": tuple(str(name) for name in need.get("alias") or ()),
                "grams": grams,
            }
        else:
            current["grams"] = current["grams"] + grams
    purchases: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for food_id, item in sorted(totals.items(), key=lambda pair: str(pair[1]["name"])):
        name = str(item["name"])
        alias = item["alias"]
        if not isinstance(alias, tuple):
            alias = ()
        if _is_allergen(name, alias, allergies):
            excluded.append({"food_id": food_id, "food_name": name, "reason": "过敏原"})
            continue
        buy = _quantize(item["grams"] - stock.get(food_id, Decimal(0)))
        if buy <= 0:
            continue
        quantity, unit = choose_unit(buy, conversions.get(food_id, {}))
        category = item["category"] if isinstance(item["category"], str) and item["category"] else _UNCATEGORIZED
        purchases.append(
            {
                "food_id": food_id,
                "name": name,
                "category": category,
                "amount_g": buy,
                "quantity": quantity,
                "unit": unit,
            }
        )
    return purchases, excluded


def choose_unit(amount: Decimal, conversions: dict[str, Decimal]) -> tuple[Decimal, str]:
    choices: list[tuple[Decimal, str, Decimal]] = []
    for unit, grams in conversions.items():
        if unit == "克" or grams <= 0:
            continue
        quotient = amount / grams
        whole = quotient.to_integral_value(rounding=ROUND_HALF_UP)
        if quotient == whole and whole > 0:
            choices.append((grams, unit, whole))
    if choices:
        _grams, unit, whole = max(choices, key=lambda item: item[0])
        return whole, unit
    return amount, "克"


def scale_grams(
    amount_g: Decimal | None,
    recipe_servings: Decimal | None,
    plan_servings: Decimal | None,
) -> Decimal | None:
    if amount_g is None:
        return None
    base = recipe_servings if recipe_servings else Decimal(1)
    if base == 0:
        base = Decimal(1)
    factor = plan_servings if plan_servings else Decimal(1)
    return amount_g / base * factor


def _planned_needs(
    session: Session, user_id: int, start: date, end: date
) -> list[dict[str, object]]:
    plans = session.execute(
        select(MealPlan, Recipe)
        .join(Recipe, MealPlan.recipe_id == Recipe.id)
        .where(MealPlan.user_id == user_id, MealPlan.date >= start, MealPlan.date <= end)
    ).all()
    recipe_ids = [recipe.id for _plan, recipe in plans]
    if not recipe_ids:
        return []
    grouped: dict[int, list[tuple[RecipeIngredient, Food]]] = {}
    rows = session.execute(
        select(RecipeIngredient, Food)
        .join(Food, RecipeIngredient.food_id == Food.id)
        .where(RecipeIngredient.recipe_id.in_(recipe_ids))
    ).all()
    for ingredient, food in rows:
        grouped.setdefault(ingredient.recipe_id, []).append((ingredient, food))
    needs: list[dict[str, object]] = []
    for plan, recipe in plans:
        for ingredient, food in grouped.get(recipe.id, []):
            grams = scale_grams(ingredient.amount_g, recipe.servings, plan.servings)
            if grams is None:
                continue
            needs.append(
                {
                    "food_id": food.id,
                    "name": food.name,
                    "category": food.category,
                    "alias": tuple(str(name) for name in food.alias or []),
                    "grams": grams,
                }
            )
    return needs


def _stock_grams(session: Session, user_id: int, today: date) -> dict[int, Decimal]:
    totals: dict[int, Decimal] = {}
    rows = list_items(session, user_id)
    factors = conversions_for(session, [item.food_id for item, _food in rows])
    for item, _food in rows:
        if expiry_status(item.expires_at, today) == "expired":
            continue
        conversion = factors.get((item.food_id, item.unit))
        if conversion is None:
            continue
        totals[item.food_id] = totals.get(item.food_id, Decimal(0)) + (
            item.quantity * conversion.grams_per_unit
        )
    return totals


def _conversion_map(
    session: Session, food_ids: list[int]
) -> dict[int, dict[str, Decimal]]:
    grouped: dict[int, dict[str, Decimal]] = {}
    for (food_id, unit), conversion in conversions_for(session, food_ids).items():
        grouped.setdefault(food_id, {})[unit] = conversion.grams_per_unit
    return grouped


def _allergies(session: Session, user_id: int) -> list[str]:
    profile = get_by_user_id(session, user_id)
    if profile is None:
        return []
    return [str(item) for item in profile.allergies or []]


def _is_allergen(name: str, alias: tuple[str, ...], allergies: list[str]) -> bool:
    names = [name, *alias]
    for needle in allergies:
        token = needle.strip()
        if token and any(token == item or token in item for item in names):
            return True
    return False


def _owned_list(session: Session, user_id: int, list_id: int) -> ShoppingList:
    shopping = session.get(ShoppingList, list_id)
    if shopping is None or shopping.user_id != user_id:
        raise ShoppingError(status_code=404, detail="找不到这份清单", code="list_not_found")
    return shopping


def _payload(
    session: Session,
    shopping: ShoppingList,
    start: date,
    end: date,
    excluded: list[dict[str, object]],
) -> dict[str, object]:
    rows = _item_rows(session, shopping.id)
    conversions = _conversion_map(session, [item.food_id for item, _food in rows])
    grouped: dict[str, list[dict[str, object]]] = {}
    for item, food in rows:
        view = _item_view(item, food, conversions.get(item.food_id, {}))
        grouped.setdefault(str(view["category"]), []).append(view)
    categories = sorted(grouped, key=lambda name: (name == _UNCATEGORIZED, name))
    return {
        "id": shopping.id,
        "start": start,
        "end": end,
        "groups": [{"category": name, "items": grouped[name]} for name in categories],
        "excluded": excluded,
    }


def _item_rows(session: Session, list_id: int) -> list[tuple[ShoppingItem, Food]]:
    rows = session.execute(
        select(ShoppingItem, Food)
        .join(Food, ShoppingItem.food_id == Food.id)
        .where(ShoppingItem.shopping_list_id == list_id)
        .order_by(Food.name)
    ).all()
    return [(item, food) for item, food in rows]


def _item_view(
    item: ShoppingItem,
    food: Food | None,
    conversions: dict[str, Decimal],
) -> dict[str, object]:
    name = food.name if food is not None else ""
    category = food.category if food is not None and food.category else _UNCATEGORIZED
    quantity, unit = choose_unit(item.amount_g, conversions)
    return {
        "id": item.id,
        "food_id": item.food_id,
        "food_name": name,
        "category": category,
        "amount_g": float(item.amount_g),
        "quantity": float(quantity),
        "unit": unit,
        "checked": bool(item.checked),
    }


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
