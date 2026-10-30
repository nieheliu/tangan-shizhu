"""按食材克数计算一份食谱的营养、主食 GI 分级和粗估 GL。

营养只来自传入的食材数字，不在这里编造。某一列只要有一条食材是空，整列就是空。
食谱里已经有油时用食谱克数。没有油时才查烹调油表；表里克数为空就不补油。
"""

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.rules.engine import GI_HIGH_MIN as RULE_GI_HIGH_MIN

GI_LOW_MAX = Decimal(55)
GI_HIGH_MIN = Decimal(RULE_GI_HIGH_MIN)
GI_BAND_SOURCE = "待核对"
_QUANTUM = Decimal("0.01")
_OIL_CSV = Path(__file__).resolve().parents[3] / "data" / "processed" / "cooking_oil.csv"
_NUTRIENTS = ("kcal", "carb_g", "protein_g", "fat_g", "fiber_g", "sodium_mg")
_OIL_NUTRIENTS = ("kcal", "fat_g")
_cache: dict[int, "RecipeNutrition"] = {}


@dataclass(frozen=True)
class IngredientLine:
    food_id: int
    name: str
    amount_g: Decimal
    per_g: Decimal
    is_main: bool
    is_oil: bool
    kcal: Decimal | None
    carb_g: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    fiber_g: Decimal | None
    sodium_mg: Decimal | None
    gi: Decimal | None
    gi_source: str | None


@dataclass(frozen=True)
class OilNutrients:
    """默认烹调油每 per_g 克的热量和脂肪。克数来自烹调油表，不写在这里。"""

    per_g: Decimal
    kcal: Decimal | None
    fat_g: Decimal | None


@dataclass(frozen=True)
class NutrientComplete:
    kcal: bool
    carb_g: bool
    protein_g: bool
    fat_g: bool
    fiber_g: bool
    sodium_mg: bool


@dataclass(frozen=True)
class RecipeNutrition:
    kcal: Decimal | None
    carb_g: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    fiber_g: Decimal | None
    sodium_mg: Decimal | None
    nutrient_complete: NutrientComplete
    oil_estimated: bool
    oil_source: str | None
    oil_grams: Decimal | None
    main_staple_food_id: int | None
    main_staple_name: str | None
    main_staple_gi: Decimal | None
    gi_source: str | None
    gi_band: str | None
    gi_band_label: str | None
    gi_band_source: str
    gl_estimate: Decimal | None
    gl_is_approximate: bool


def is_cooking_oil(category: str | None) -> bool:
    if not category:
        return False
    return category == "油脂" or category.startswith(("植物油", "动物油脂"))


def load_cooking_oil(
    path: Path | None = None,
) -> dict[str, tuple[Decimal | None, str]]:
    table: dict[str, tuple[Decimal | None, str]] = {}
    with (path or _OIL_CSV).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("grams") or "").strip()
            source = (row.get("source") or "").strip() or GI_BAND_SOURCE
            table[row["cooking_method"].strip()] = (
                Decimal(raw) if raw else None,
                source,
            )
    return table


def clear_recipe_nutrition_cache() -> None:
    _cache.clear()


def calculate_recipe_nutrition(
    ingredients: Sequence[IngredientLine],
    *,
    servings: Decimal | None = None,
    cooking_method: str | None = None,
    oil_table: Mapping[str, tuple[Decimal | None, str]] | None = None,
    default_oil: OilNutrients | None = None,
    recipe_id: int | None = None,
) -> RecipeNutrition:
    if recipe_id is not None and recipe_id in _cache:
        return _cache[recipe_id]
    result = _calculate(
        ingredients,
        servings=_servings(servings),
        cooking_method=cooking_method,
        oil_table=oil_table if oil_table is not None else load_cooking_oil(),
        default_oil=default_oil,
    )
    if recipe_id is not None:
        _cache[recipe_id] = result
    return result


def gi_band(gi: Decimal | None) -> tuple[str | None, str | None]:
    if gi is None:
        return None, None
    if gi <= GI_LOW_MAX:
        return "low", "低"
    if gi >= GI_HIGH_MIN:
        return "high", "高"
    return "medium", "中"


def _calculate(
    ingredients: Sequence[IngredientLine],
    *,
    servings: Decimal,
    cooking_method: str | None,
    oil_table: Mapping[str, tuple[Decimal | None, str]],
    default_oil: OilNutrients | None,
) -> RecipeNutrition:
    totals: dict[str, Decimal | None] = {}
    complete: dict[str, bool] = {}
    for field in _NUTRIENTS:
        parts: list[Decimal] = []
        missing = False
        for item in ingredients:
            value = getattr(item, field)
            if value is None:
                missing = True
                break
            parts.append(_scaled(item.amount_g, item.per_g, value))
        if missing:
            totals[field] = None
            complete[field] = False
        else:
            totals[field] = sum(parts, start=Decimal(0))
            complete[field] = True

    oil_estimated = False
    oil_source: str | None = None
    oil_grams: Decimal | None = None
    if not any(item.is_oil for item in ingredients):
        row = oil_table.get(cooking_method or "")
        oil_source = row[1] if row is not None else GI_BAND_SOURCE
        grams = row[0] if row is not None else None
        if grams is not None:
            oil_estimated = True
            oil_grams = grams
            _add_default_oil(totals, complete, grams, default_oil)

    portion = {
        field: None if totals[field] is None else _quantize(totals[field] / servings)
        for field in _NUTRIENTS
    }
    staple = _staple(ingredients)
    staple_carb = _staple_carb(staple, servings)
    band, label = gi_band(None if staple is None else staple.gi)
    gl = None
    if staple is not None and staple.gi is not None and staple_carb is not None:
        gl = _quantize(staple.gi * staple_carb / Decimal(100))
    return RecipeNutrition(
        kcal=portion["kcal"],
        carb_g=portion["carb_g"],
        protein_g=portion["protein_g"],
        fat_g=portion["fat_g"],
        fiber_g=portion["fiber_g"],
        sodium_mg=portion["sodium_mg"],
        nutrient_complete=NutrientComplete(
            kcal=complete["kcal"],
            carb_g=complete["carb_g"],
            protein_g=complete["protein_g"],
            fat_g=complete["fat_g"],
            fiber_g=complete["fiber_g"],
            sodium_mg=complete["sodium_mg"],
        ),
        oil_estimated=oil_estimated,
        oil_source=oil_source,
        oil_grams=oil_grams,
        main_staple_food_id=None if staple is None else staple.food_id,
        main_staple_name=None if staple is None else staple.name,
        main_staple_gi=None if staple is None else staple.gi,
        gi_source=None if staple is None else staple.gi_source,
        gi_band=band,
        gi_band_label=label,
        gi_band_source=GI_BAND_SOURCE,
        gl_estimate=gl,
        gl_is_approximate=True,
    )


def _add_default_oil(
    totals: dict[str, Decimal | None],
    complete: dict[str, bool],
    grams: Decimal,
    default_oil: OilNutrients | None,
) -> None:
    for field in _OIL_NUTRIENTS:
        if not complete[field] or totals[field] is None:
            continue
        nutrient = None if default_oil is None else getattr(default_oil, field)
        if nutrient is None or default_oil is None:
            totals[field] = None
            complete[field] = False
            continue
        totals[field] = totals[field] + _scaled(grams, default_oil.per_g, nutrient)


def _staple(ingredients: Sequence[IngredientLine]) -> IngredientLine | None:
    candidates = [item for item in ingredients if item.is_main and item.gi is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.amount_g, -item.food_id))


def _staple_carb(staple: IngredientLine | None, servings: Decimal) -> Decimal | None:
    if staple is None or staple.carb_g is None:
        return None
    return _quantize(_scaled(staple.amount_g, staple.per_g, staple.carb_g) / servings)


def _scaled(amount_g: Decimal, per_g: Decimal, value: Decimal) -> Decimal:
    if per_g <= 0:
        raise ValueError("每份基准克数必须大于 0")
    return amount_g / per_g * value


def _servings(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal(1)
    if value <= 0:
        raise ValueError("份数必须大于 0")
    return value


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
