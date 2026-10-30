from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Food, FoodUnitConversion, InventoryItem


def search_foods(session: Session, keyword: str, limit: int) -> list[Food]:
    text = keyword.strip()
    if not text:
        return []
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    statement = (
        select(Food)
        .where(Food.name.ilike(f"%{escaped}%", escape="\\"))
        .order_by(Food.name)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def conversions_for(
    session: Session, food_ids: list[int]
) -> dict[tuple[int, str], FoodUnitConversion]:
    if not food_ids:
        return {}
    rows = session.scalars(
        select(FoodUnitConversion).where(FoodUnitConversion.food_id.in_(food_ids))
    ).all()
    return {(row.food_id, row.unit): row for row in rows}


def get_food(session: Session, food_id: int) -> Food | None:
    return session.get(Food, food_id)


def get_conversion(
    session: Session, food_id: int, unit: str
) -> FoodUnitConversion | None:
    return session.scalars(
        select(FoodUnitConversion).where(
            FoodUnitConversion.food_id == food_id,
            FoodUnitConversion.unit == unit,
        )
    ).one_or_none()


def list_items(session: Session, user_id: int) -> list[tuple[InventoryItem, Food]]:
    statement = (
        select(InventoryItem, Food)
        .join(Food, Food.id == InventoryItem.food_id)
        .where(InventoryItem.user_id == user_id)
        .order_by(InventoryItem.expires_at.asc().nulls_last(), Food.name.asc())
    )
    return [(item, food) for item, food in session.execute(statement).all()]


def list_due(
    session: Session, user_id: int, today: date
) -> list[tuple[InventoryItem, Food]]:
    deadline = today + timedelta(days=2)
    statement = (
        select(InventoryItem, Food)
        .join(Food, Food.id == InventoryItem.food_id)
        .where(
            InventoryItem.user_id == user_id,
            InventoryItem.expires_at.is_not(None),
            InventoryItem.expires_at <= deadline,
        )
        .order_by(InventoryItem.expires_at.asc(), Food.name.asc())
    )
    return [(item, food) for item, food in session.execute(statement).all()]


def count_due(session: Session, today: date) -> int:
    deadline = today + timedelta(days=2)
    total = session.scalar(
        select(func.count())
        .select_from(InventoryItem)
        .where(
            InventoryItem.expires_at.is_not(None),
            InventoryItem.expires_at <= deadline,
        )
    )
    return int(total or 0)


def get_item(session: Session, user_id: int, item_id: int) -> InventoryItem | None:
    return session.scalars(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.user_id == user_id,
        )
    ).one_or_none()


def save_item(session: Session, item: InventoryItem) -> InventoryItem:
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_item(session: Session, item: InventoryItem) -> None:
    session.delete(item)
    session.commit()
