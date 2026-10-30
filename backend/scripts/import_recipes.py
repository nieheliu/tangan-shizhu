"""导入食谱，并把对不上食物库的食材写到 unmatched.csv。"""

import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models.entities import Food, Recipe, RecipeIngredient
from app.services.food_catalog import normalize_food_name

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
UNMATCHED = PROCESSED / "unmatched.csv"


def _rows(name: str) -> list[dict[str, str]]:
    with (PROCESSED / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_unmatched() -> list[list[str]]:
    if not UNMATCHED.exists():
        return []
    with UNMATCHED.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return [row for row in rows[1:] if row and row[0] != "recipe_ingredient"]


def _write_unmatched(rows: list[list[str]]) -> None:
    with UNMATCHED.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kind", "name", "detail"])
        writer.writerows(rows)


def import_recipes(session: Session) -> dict[str, int]:
    foods = {
        normalize_food_name(food.name): food for food in session.scalars(select(Food))
    }
    recipes = {recipe.name: recipe for recipe in session.scalars(select(Recipe))}
    created = 0
    for row in _rows("recipes.csv"):
        if row["name"] in recipes:
            continue
        recipe = Recipe(
            name=row["name"],
            cuisine=row["cuisine"] or None,
            meal_types=[item for item in row["meal_types"].split("|") if item],
            cooking_method=row["cooking_method"] or None,
            steps=row["steps"] or None,
            servings=Decimal(row["servings"]),
            source=row["source"] or "待核对",
        )
        session.add(recipe)
        recipes[recipe.name] = recipe
        created += 1
    session.flush()

    linked = 0
    unmatched: list[list[str]] = []
    for row in _rows("recipe_ingredients.csv"):
        recipe = recipes.get(row["recipe_name"])
        food = foods.get(normalize_food_name(row["food_name"]))
        if recipe is None or food is None:
            unmatched.append(
                [
                    "recipe_ingredient",
                    row["food_name"],
                    f"食谱 {row['recipe_name']} 找不到食材",
                ]
            )
            continue
        existing = session.scalars(
            select(RecipeIngredient).where(
                RecipeIngredient.recipe_id == recipe.id,
                RecipeIngredient.food_id == food.id,
            )
        ).one_or_none()
        if existing is None:
            session.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    food_id=food.id,
                    amount_g=Decimal(row["amount_g"]),
                    is_main=row["is_main"] == "1",
                )
            )
            linked += 1
    _write_unmatched([*(_read_unmatched()), *unmatched])
    return {"recipes": created, "ingredients": linked, "unmatched": len(unmatched)}


def main() -> None:
    with get_sessionmaker()() as session:
        stats = import_recipes(session)
        session.commit()
    print(
        f"recipes={stats['recipes']} ingredients={stats['ingredients']} unmatched={stats['unmatched']}"
    )


if __name__ == "__main__":
    main()
