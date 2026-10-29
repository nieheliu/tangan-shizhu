import csv
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "processed"

NUTRIENT_COLUMNS = {
    "kcal",
    "carb_g",
    "protein_g",
    "fat_g",
    "fiber_g",
    "sodium_mg",
    "gi",
}


def _rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_seed_files_omit_unverified_nutrients() -> None:
    foods = _rows("foods.csv")
    recipes = _rows("recipes.csv")
    ingredients = _rows("recipe_ingredients.csv")
    oils = _rows("cooking_oil.csv")
    units = _rows("unit_conversions.csv")

    assert len(foods) == 30
    assert NUTRIENT_COLUMNS.isdisjoint(foods[0])
    assert len(recipes) == 20
    assert {row["source"] for row in recipes} == {"待核对"}
    food_names = {row["name"] for row in foods}
    assert {row["food_name"] for row in ingredients} <= food_names
    assert {row["recipe_name"] for row in ingredients} <= {
        row["name"] for row in recipes
    }
    assert all(row["grams"].strip() == "" and row["source"] == "待核对" for row in oils)
    filled_units = [row for row in units if row["grams_per_unit"].strip()]
    assert filled_units
    assert all(
        row["unit"] == "克" and row["grams_per_unit"] == "1" for row in filled_units
    )
    pending_units = [row for row in units if not row["grams_per_unit"].strip()]
    assert pending_units
    assert all(row["source"] == "待核对" for row in pending_units)
