"""把成分表和 GI 表整理成可入库的记录。不猜测缺失数字。"""

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

NUTRIENT_SOURCE = "《中国食物成分表》标准版第6版一般营养成分；社区转录 fixed_en 2026-08-25；未对照纸质书"
GI_SOURCE = "《中国食物成分表》标准版第6版附表GI，杨月欣2018；社区json未对照纸质书"
_MISSING = {"", "—", "-", "－", "tr"}


@dataclass
class FoodRecord:
    food_code: str
    name: str
    category: str
    alias: list[str]
    kcal: Decimal | None
    carb_g: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    fiber_g: Decimal | None
    sodium_mg: Decimal | None


@dataclass
class GiRecord:
    name: str
    category: str
    gi: Decimal


@dataclass
class Catalog:
    foods: list[FoodRecord] = field(default_factory=list)
    gi: list[GiRecord] = field(default_factory=list)
    conflicts: list[tuple[str, str]] = field(default_factory=list)


def normalize_food_name(name: str) -> str:
    text = name.strip().replace("\u3000", " ")
    while text.startswith("*"):
        text = text[1:].strip()
    return " ".join(text.split())


def parse_nutrient(raw: str) -> Decimal | None:
    text = raw.strip()
    if text.lower() in _MISSING:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def composition_records(rows: list[dict[str, str]]) -> list[FoodRecord]:
    counts = Counter(normalize_food_name(row["foodName"]) for row in rows)
    records: list[FoodRecord] = []
    for row in rows:
        base = normalize_food_name(row["foodName"])
        name = base if counts[base] == 1 else f"{base}〔{row['foodCode']}〕"
        english = row.get("englishName", "").strip()
        records.append(
            FoodRecord(
                food_code=row["foodCode"].strip(),
                name=name,
                category=row.get("category", "").strip(),
                alias=[english] if english else [],
                kcal=parse_nutrient(row.get("energyKCal", "")),
                carb_g=parse_nutrient(row.get("CHO", "")),
                protein_g=parse_nutrient(row.get("protein", "")),
                fat_g=parse_nutrient(row.get("fat", "")),
                fiber_g=parse_nutrient(row.get("dietaryFiber", "")),
                sodium_mg=parse_nutrient(row.get("Na", "")),
            )
        )
    return records


def gi_records(
    groups: list[dict[str, object]],
) -> tuple[list[GiRecord], list[tuple[str, str]]]:
    grouped: dict[str, list[tuple[str, Decimal, str]]] = {}
    for group in groups:
        category = str(group.get("foodGroup", "")).strip()
        items = group.get("list", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = normalize_food_name(str(item.get("foodName", "")))
            gi = parse_nutrient(str(item.get("GI", "")))
            if not name or gi is None:
                continue
            grouped.setdefault(name, []).append((name, gi, category))
    ready: list[GiRecord] = []
    conflicts: list[tuple[str, str]] = []
    for name, values in grouped.items():
        gis = {value[1] for value in values}
        if len(gis) > 1:
            conflicts.append((name, "同名 GI 不一致，未入库"))
            continue
        ready.append(GiRecord(name=name, category=values[0][2], gi=values[0][1]))
    return ready, conflicts
