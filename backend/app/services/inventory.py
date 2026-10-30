"""冰箱库存。克数由换算表算出，没有换算的单位直接拒绝。"""

import logging
import os
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.entities import Food, InventoryItem
from app.repositories.inventory import (
    conversions_for,
    count_due,
    delete_item,
    get_conversion,
    get_food,
    get_item,
    list_due,
    list_items,
    save_item,
    search_foods,
)
from app.schemas.inventory import FoodOption, InventoryItemView, InventoryWrite

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


class InventoryError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def today_in_app_tz() -> date:
    zone = ZoneInfo(get_settings().app_timezone)
    return datetime.now(zone).date()


def expiry_status(expires_at: date | None, today: date) -> str:
    if expires_at is None:
        return "unknown"
    if expires_at < today:
        return "expired"
    if expires_at <= today + timedelta(days=2):
        return "expiring"
    return "ok"


def search_food_options(session: Session, keyword: str, limit: int) -> list[FoodOption]:
    foods = search_foods(session, keyword, limit)
    factors = conversions_for(session, [food.id for food in foods])
    options: list[FoodOption] = []
    for food in foods:
        units = sorted(unit for food_id, unit in factors if food_id == food.id)
        options.append(
            FoodOption(
                id=food.id,
                name=food.name,
                category=food.category,
                units=units,
            )
        )
    return options


def list_inventory(session: Session, user_id: int) -> list[InventoryItemView]:
    return _views(session, list_items(session, user_id), today_in_app_tz())


def list_reminders(session: Session, user_id: int) -> list[InventoryItemView]:
    today = today_in_app_tz()
    return _views(session, list_due(session, user_id, today), today)


def create_item(session: Session, user_id: int, body: InventoryWrite) -> InventoryItemView:
    return _save(session, user_id, body, existing=None)


def update_item(
    session: Session, user_id: int, item_id: int, body: InventoryWrite
) -> InventoryItemView:
    existing = get_item(session, user_id, item_id)
    if existing is None:
        raise InventoryError(status_code=404, detail="找不到这条库存", code="not_found")
    return _save(session, user_id, body, existing)


def remove_item(session: Session, user_id: int, item_id: int) -> None:
    existing = get_item(session, user_id, item_id)
    if existing is None:
        raise InventoryError(status_code=404, detail="找不到这条库存", code="not_found")
    delete_item(session, existing)


def run_expiry_check() -> int:
    """每天扫一遍到期日。页面上的颜色按当天日期现算，不依赖这次任务已经跑过。"""
    today = today_in_app_tz()
    try:
        session_factory = get_sessionmaker()
        with session_factory() as session:
            total = count_due(session, today)
    except Exception:
        logger.exception("临期检查失败")
        return 0
    record_audit(
        action="inventory.expiry_check",
        target="inventory",
        request_id="scheduler",
        detail={"count": total, "date": today.isoformat()},
    )
    return total


def start_expiry_scheduler() -> None:
    global _scheduler
    if os.environ.get("PYTEST_CURRENT_TEST") or _scheduler is not None:
        return
    scheduler = BackgroundScheduler(timezone=get_settings().app_timezone)
    scheduler.add_job(
        run_expiry_check,
        trigger="cron",
        hour=8,
        minute=0,
        id="inventory-expiry",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler


def stop_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def _save(
    session: Session,
    user_id: int,
    body: InventoryWrite,
    existing: InventoryItem | None,
) -> InventoryItemView:
    food = get_food(session, body.food_id)
    if food is None:
        raise InventoryError(status_code=404, detail="找不到这种食材", code="food_not_found")
    conversion = get_conversion(session, body.food_id, body.unit)
    if conversion is None:
        raise InventoryError(
            status_code=422,
            detail=f"没有「{body.unit}」的换算，请改成克",
            code="unknown_unit",
        )
    item = existing or InventoryItem(user_id=user_id, food_id=body.food_id)
    item.food_id = body.food_id
    item.quantity = body.quantity
    item.unit = body.unit
    item.purchased_at = body.purchased_at
    item.expires_at = body.expires_at
    saved = save_item(session, item)
    grams = _grams(saved.quantity, conversion.grams_per_unit)
    return _view(saved, food, grams, today_in_app_tz())


def _views(
    session: Session,
    rows: list[tuple[InventoryItem, Food]],
    today: date,
) -> list[InventoryItemView]:
    factors = conversions_for(session, [item.food_id for item, _food in rows])
    views: list[InventoryItemView] = []
    for item, food in rows:
        conversion = factors.get((item.food_id, item.unit))
        grams = None
        if conversion is not None:
            grams = _grams(item.quantity, conversion.grams_per_unit)
        views.append(_view(item, food, grams, today))
    return views


def _view(
    item: InventoryItem,
    food: Food,
    grams: float | None,
    today: date,
) -> InventoryItemView:
    return InventoryItemView(
        id=item.id,
        food_id=item.food_id,
        food_name=food.name,
        quantity=_quantity(item.quantity),
        unit=item.unit,
        grams=grams,
        purchased_at=item.purchased_at,
        expires_at=item.expires_at,
        status=expiry_status(item.expires_at, today),
    )


def _grams(quantity: Decimal, grams_per_unit: Decimal) -> float:
    total = (quantity * grams_per_unit).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(total)


def _quantity(quantity: Decimal) -> float:
    return float(quantity.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
