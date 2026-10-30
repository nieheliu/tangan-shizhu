from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.graph.sync import (
    GraphDataError,
    contains_row,
    food_properties,
    load_relations,
    recipe_properties,
)
from app.models.entities import Food, Recipe


def test_food_node_keeps_identity_and_drops_nutrients() -> None:
    food = Food(
        id=3,
        name="燕麦",
        category="主食",
        kcal=Decimal(367),
        gi=Decimal(55),
        carb_g=Decimal("66.9"),
    )
    assert food_properties(food) == {"name": "燕麦", "category": "主食", "pg_id": 3}


def test_recipe_node_and_contains_edge_have_no_amounts() -> None:
    recipe = Recipe(id=8, name="燕麦粥", cooking_method="煮", servings=Decimal(1))
    assert recipe_properties(recipe) == {"name": "燕麦粥", "pg_id": 8}
    assert contains_row(8, 3) == {"recipe_id": 8, "food_id": 3}
    assert "amount_g" not in contains_row(8, 3)


def test_cited_relations_keep_only_stated_limits() -> None:
    rows = load_relations()
    assert Counter(row.kind for row in rows) == {
        "RECOMMEND": 20,
        "SUBSTITUTE": 7,
        "AVOID": 1,
        "AVOID_METHOD": 2,
        "LIMIT": 3,
    }
    assert all("成人糖尿病食养指南" in row.source for row in rows)
    limits = {row.to_name: row for row in rows if row.kind == "LIMIT"}
    assert limits["烹调油"].max_per_day == 25
    assert limits["烹调油"].unit == "g"
    assert limits["食盐"].max_per_day == 5
    assert limits["糖"].max_per_day is None
    assert all(row.max_per_day != 0 for row in rows)
    assert any(row.kind == "RECOMMEND" and row.to_name == "燕麦" for row in rows)
    assert any(row.kind == "AVOID" and row.to_name == "含糖饮料" for row in rows)


def test_blank_limit_is_not_stored_as_zero(tmp_path: Path) -> None:
    path = tmp_path / "relations.csv"
    path.write_text(
        "kind,from_name,to_name,reason,source,max_per_day,unit\n"
        "LIMIT,2型糖尿病,糖,少糖,出处,,\n",
        encoding="utf-8",
    )
    assert load_relations(path)[0].max_per_day is None


def test_relation_without_source_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "relations.csv"
    path.write_text(
        "kind,from_name,to_name,reason,source,max_per_day,unit\n"
        "AVOID,2型糖尿病,白糖,没有出处,,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(GraphDataError, match="出处"):
        load_relations(path)
