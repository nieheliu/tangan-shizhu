"""写入演示数据。营养素和 GI 留空，烹调油克数未核对的不入库。"""

import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.models.entities import (
    Food,
    FoodUnitConversion,
    HealthProfile,
    Recipe,
    RecipeIngredient,
    User,
)

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data" / "processed"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo12345"
DEMO_BIRTH_YEAR = 1990


def _rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _split(value: str) -> list[str]:
    return [item for item in value.split("|") if item]


def _foods(session: Session) -> dict[str, Food]:
    existing = {food.name: food for food in session.scalars(select(Food))}
    for row in _rows("foods.csv"):
        if row["name"] in existing:
            continue
        alias = (
            [item for item in row["alias"].split("|") if item] if row["alias"] else []
        )
        food = Food(
            name=row["name"], alias=alias, category=row["category"], gi_source="待核对"
        )
        session.add(food)
        existing[food.name] = food
    session.flush()
    return existing


def _units(session: Session, foods: dict[str, Food]) -> None:
    for row in _rows("unit_conversions.csv"):
        grams = row["grams_per_unit"].strip()
        if not grams:
            continue
        food = foods[row["food_name"]]
        already = session.scalars(
            select(FoodUnitConversion).where(
                FoodUnitConversion.food_id == food.id,
                FoodUnitConversion.unit == row["unit"],
            )
        ).one_or_none()
        if already is not None:
            continue
        session.add(
            FoodUnitConversion(
                food_id=food.id,
                unit=row["unit"],
                grams_per_unit=Decimal(grams),
            )
        )
    session.flush()


def _recipes(session: Session, foods: dict[str, Food]) -> None:
    existing = {recipe.name: recipe for recipe in session.scalars(select(Recipe))}
    for row in _rows("recipes.csv"):
        if row["name"] in existing:
            continue
        recipe = Recipe(
            name=row["name"],
            cuisine=row["cuisine"] or None,
            meal_types=_split(row["meal_types"]),
            cooking_method=row["cooking_method"] or None,
            steps=row["steps"] or None,
            servings=Decimal(row["servings"]),
            source=row["source"],
        )
        session.add(recipe)
        existing[recipe.name] = recipe
    session.flush()
    for row in _rows("recipe_ingredients.csv"):
        recipe = existing[row["recipe_name"]]
        food = foods[row["food_name"]]
        already = session.scalars(
            select(RecipeIngredient).where(
                RecipeIngredient.recipe_id == recipe.id,
                RecipeIngredient.food_id == food.id,
            )
        ).one_or_none()
        if already is not None:
            continue
        session.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                food_id=food.id,
                amount_g=Decimal(row["amount_g"]),
                is_main=row["is_main"] == "1",
            )
        )
    session.flush()


def _demo_user(session: Session) -> None:
    user = session.scalars(
        select(User).where(User.username == DEMO_USERNAME)
    ).one_or_none()
    if user is None:
        user = User(
            username=DEMO_USERNAME,
            password_hash=hash_password(DEMO_PASSWORD),
            role="user",
        )
        session.add(user)
        session.flush()
    profile = session.scalars(
        select(HealthProfile).where(HealthProfile.user_id == user.id)
    ).one_or_none()
    if profile is None:
        session.add(
            HealthProfile(
                user_id=user.id,
                gender="女",
                birth_year=DEMO_BIRTH_YEAR,
                activity_level="中",
                diseases=["2型糖尿病"],
            )
        )
    session.flush()


def seed(session: Session) -> None:
    foods = _foods(session)
    _units(session, foods)
    _recipes(session, foods)
    _demo_user(session)


def main() -> None:
    session_factory = get_sessionmaker()
    with session_factory() as session:
        seed(session)
        session.commit()
        foods = session.scalar(select(func.count()).select_from(Food))
        recipes = session.scalar(select(func.count()).select_from(Recipe))
        print(f"foods={foods} recipes={recipes} user={DEMO_USERNAME}")


if __name__ == "__main__":
    main()
