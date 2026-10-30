"""营养报告。合计和供能比由这里计算，模型只能复述这些数字。"""

import json
import re
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.prompts import REPORT_SYSTEM
from app.core.llm import generate
from app.models.entities import MealPlan, Recipe
from app.rag.embeddings import embed_texts
from app.rag.retrieve import search_guidelines
from app.rag.vectorstore import chroma_directory, get_collection, open_client
from app.repositories.profiles import get_by_user_id
from app.services.inventory import today_in_app_tz
from app.services.meal_plans import MEAL_TYPES
from app.services.nutrition import KCAL_SOURCE
from app.services.recipes import recipe_nutrition

_QUANTUM = Decimal("0.01")
_CARB_KCAL = Decimal(4)
_PROTEIN_KCAL = Decimal(4)
_FAT_KCAL = Decimal(9)
_ENERGY_SOURCE = "待核对"
_FIBER_SOURCE = "待核对"
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_PERCENT_RANGE = re.compile(r"\d+(?:\.\d+)?\s*[%％]\s*[~～\-—到至]\s*\d+")
_FIELDS = ("kcal", "carb_g", "protein_g", "fat_g", "fiber_g", "sodium_mg", "gl_estimate")


def daily_report(session: Session, user_id: int, day: date | None = None) -> dict[str, object]:
    report_day = day or today_in_app_tz()
    target, target_source = _target(session, user_id)
    dishes = _dishes(session, user_id, report_day)
    return assemble_daily(report_day, dishes, target, target_source)


def weekly_report(session: Session, user_id: int, end: date | None = None) -> dict[str, object]:
    report_end = end or today_in_app_tz()
    days = [
        daily_report(session, user_id, report_end - timedelta(days=offset))
        for offset in range(6, -1, -1)
    ]
    return assemble_weekly(report_end, days)


def explain_report(
    session: Session,
    user_id: int,
    *,
    scope: str,
    day: date | None = None,
) -> dict[str, object]:
    if scope == "daily":
        report: dict[str, object] = daily_report(session, user_id, day)
    elif scope == "weekly":
        report = weekly_report(session, user_id, day)
    else:
        raise ValueError(scope)
    rag, chunks = _retrieve("糖尿病成人一天的主食和碳水化合物")
    summary, citations = _explain(report, chunks)
    return {"summary": summary, "citation_ids": citations, "rag": rag}


def assemble_daily(
    day: date,
    dishes: list[dict[str, object]],
    kcal_target: int | None,
    kcal_target_source: str,
) -> dict[str, object]:
    ordered = sorted(dishes, key=lambda item: (_rank(str(item["meal_type"])), int(item["meal_plan_id"])))
    totals = {field: _sum(item.get(field) for item in ordered) for field in _FIELDS}
    ratios = _ratios(totals["carb_g"], totals["protein_g"], totals["fat_g"])
    hints = _daily_hints(ordered, totals, ratios, kcal_target, kcal_target_source)
    return {
        "date": day,
        "meal_count": len(ordered),
        "kcal_target": kcal_target,
        "kcal_target_source": kcal_target_source,
        "totals": {field: _number(totals[field]) for field in _FIELDS},
        "energy_ratios": {
            "carb": _number(ratios["carb"]),
            "protein": _number(ratios["protein"]),
            "fat": _number(ratios["fat"]),
            "factor_source": _ENERGY_SOURCE,
            "target_range": None,
        },
        "fiber_target_g": None,
        "fiber_target_source": _FIBER_SOURCE,
        "fiber_met_days": None,
        "gl_is_approximate": True,
        "hints": hints,
        "items": [_item_payload(item) for item in ordered],
    }


def assemble_weekly(end: date, days: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(days, key=lambda item: item["date"])
    known = [
        Decimal(str(item["totals"]["kcal"]))
        for item in ordered
        if item["totals"]["kcal"] is not None and item["meal_count"]
    ]
    average = None if not known else _quantize(sum(known, Decimal(0)) / Decimal(len(known)))
    ratio = _weekly_ratio(ordered)
    points = [
        {
            "date": item["date"],
            "kcal": item["totals"]["kcal"],
            "carb_energy_ratio": item["energy_ratios"]["carb"],
            "fiber_g": item["totals"]["fiber_g"],
        }
        for item in ordered
    ]
    return {
        "start": end - timedelta(days=6),
        "end": end,
        "days": points,
        "kcal_average": _number(average),
        "days_with_kcal": len(known),
        "carb_energy_ratio": _number(ratio),
        "energy_factor_source": _ENERGY_SOURCE,
        "target_range": None,
        "fiber_target_g": None,
        "fiber_target_source": _FIBER_SOURCE,
        "fiber_met_days": None,
        "hints": _weekly_hints(len(known), average, ratio),
    }


def _dishes(session: Session, user_id: int, day: date) -> list[dict[str, object]]:
    rows = session.execute(
        select(MealPlan, Recipe)
        .join(Recipe, MealPlan.recipe_id == Recipe.id)
        .where(MealPlan.user_id == user_id, MealPlan.date == day)
    ).all()
    dishes: list[dict[str, object]] = []
    for plan, recipe in rows:
        nutrition = recipe_nutrition(session, recipe)
        factor = plan.servings or Decimal(1)
        dishes.append(
            {
                "meal_plan_id": plan.id,
                "recipe_id": recipe.id,
                "name": recipe.name,
                "meal_type": plan.meal_type,
                "servings": factor,
                "kcal": _times(nutrition.kcal, factor),
                "carb_g": _times(nutrition.carb_g, factor),
                "protein_g": _times(nutrition.protein_g, factor),
                "fat_g": _times(nutrition.fat_g, factor),
                "fiber_g": _times(nutrition.fiber_g, factor),
                "sodium_mg": _times(nutrition.sodium_mg, factor),
                "oil_estimated": nutrition.oil_estimated,
                "gi_band_label": nutrition.gi_band_label,
                "gi_band_source": nutrition.gi_band_source,
                "gl_estimate": _times(nutrition.gl_estimate, factor),
            }
        )
    return dishes


def _target(session: Session, user_id: int) -> tuple[int | None, str]:
    profile = get_by_user_id(session, user_id)
    if profile is None or profile.daily_kcal_target is None:
        return None, KCAL_SOURCE
    return int(profile.daily_kcal_target), KCAL_SOURCE


def _daily_hints(
    dishes: list[dict[str, object]],
    totals: dict[str, Decimal | None],
    ratios: dict[str, Decimal | None],
    kcal_target: int | None,
    kcal_target_source: str,
) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    if not dishes:
        hints.append(
            {
                "code": "plan_empty",
                "message": "这一天还没有加入计划。",
                "basis": "统计范围是当天计划里的食谱，不含计划外的饮食。",
            }
        )
        return hints
    kcal = totals["kcal"]
    if kcal is None:
        hints.append(
            {
                "code": "kcal_incomplete",
                "message": "有食谱缺少热量，今日热量无法合计，也不能和目标比较。",
                "basis": "只要有一道菜的热量是空的，当天合计就留空，不用 0 代替。",
            }
        )
    elif kcal_target is None:
        hints.append(
            {
                "code": "target_missing",
                "message": f"今日热量合计 {_show(kcal)} kcal。档案里还没有每日热量目标。",
                "basis": "热量来自计划中食谱的成分合计。",
            }
        )
    else:
        hints.append(_kcal_hint(kcal, kcal_target, kcal_target_source))
    if ratios["carb"] is None:
        hints.append(
            {
                "code": "ratio_incomplete",
                "message": "宏量营养素有缺失，供能比无法计算。",
                "basis": "碳水、蛋白质或脂肪有空值时不计算供能比。",
            }
        )
    else:
        hints.append(
            {
                "code": "ratio_ready",
                "message": (
                    f"碳水供能比 {_show(ratios['carb'])}%，"
                    f"蛋白质 {_show(ratios['protein'])}%，脂肪 {_show(ratios['fat'])}%。"
                ),
                "basis": (
                    "供能比按碳水、蛋白质每克 4 kcal、脂肪每克 9 kcal 估算，系数来源待核对。"
                    "目标区间尚未对照指南页码，这里不显示区间。"
                ),
            }
        )
    fiber = totals["fiber_g"]
    fiber_text = "缺少数据" if fiber is None else f"{_show(fiber)} g"
    hints.append(
        {
            "code": "fiber_unverified",
            "message": f"膳食纤维合计 {fiber_text}。达标克数待核对，所以不计算达标天数。",
            "basis": "达标标准还没有核对过的指南页码，不能把未核对的克数当成达标线。",
        }
    )
    if any(item["oil_estimated"] for item in dishes):
        hints.append(
            {
                "code": "oil_estimated",
                "message": "部分菜的热量和脂肪包含估算烹调油。",
                "basis": "食谱没有写明用油、且烹调油表有克数时才估算。克数仍待核对时不会凭空加。",
            }
        )
    return hints


def _kcal_hint(kcal: Decimal, target: int, source: str) -> dict[str, str]:
    goal = Decimal(target)
    if kcal > goal:
        relation = "高于"
        code = "kcal_over"
    elif kcal < goal:
        relation = "低于"
        code = "kcal_under"
    else:
        relation = "等于"
        code = "kcal_equal"
    return {
        "code": code,
        "message": f"今日热量 {_show(kcal)} kcal，{relation}每日目标 {target} kcal。",
        "basis": f"比较的是计划内食谱热量合计和档案中的每日热量目标。目标估算系数来源为{source}。",
    }


def _weekly_hints(
    days_with_kcal: int,
    average: Decimal | None,
    ratio: Decimal | None,
) -> list[dict[str, str]]:
    if days_with_kcal == 0 or average is None:
        kcal_message = "近 7 天没有可以合计热量的日期。"
    else:
        kcal_message = (
            f"近 7 天里有 {days_with_kcal} 天可以合计热量，这些天的平均热量是 {_show(average)} kcal。"
        )
    ratio_message = (
        "本周供能比无法计算。"
        if ratio is None
        else f"有完整宏量营养素的日期，碳水供能比是 {_show(ratio)}%。"
    )
    return [
        {
            "code": "week_kcal",
            "message": kcal_message,
            "basis": "没有计划或热量缺失的日期不计入平均，也不按 0 处理。",
        },
        {
            "code": "week_ratio",
            "message": ratio_message,
            "basis": (
                "供能比按碳水、蛋白质每克 4 kcal、脂肪每克 9 kcal 估算，系数来源待核对。"
                "目标区间尚未对照指南页码，这里不显示区间。"
            ),
        },
        {
            "code": "fiber_unverified",
            "message": "膳食纤维达标天数未统计，达标克数待核对。",
            "basis": "达标标准还没有核对过的指南页码。",
        },
    ]


def _weekly_ratio(days: list[dict[str, object]]) -> Decimal | None:
    carb = Decimal(0)
    protein = Decimal(0)
    fat = Decimal(0)
    used = False
    for item in days:
        ratios = item["energy_ratios"]
        totals = item["totals"]
        if not isinstance(ratios, dict) or ratios.get("carb") is None:
            continue
        if not isinstance(totals, dict):
            continue
        if item["meal_count"] == 0:
            continue
        carb += Decimal(str(totals["carb_g"]))
        protein += Decimal(str(totals["protein_g"]))
        fat += Decimal(str(totals["fat_g"]))
        used = True
    if not used:
        return None
    return _ratios(carb, protein, fat)["carb"]


def _ratios(
    carb_g: Decimal | None,
    protein_g: Decimal | None,
    fat_g: Decimal | None,
) -> dict[str, Decimal | None]:
    empty = {"carb": None, "protein": None, "fat": None}
    if carb_g is None or protein_g is None or fat_g is None:
        return empty
    carb_kcal = carb_g * _CARB_KCAL
    protein_kcal = protein_g * _PROTEIN_KCAL
    fat_kcal = fat_g * _FAT_KCAL
    total = carb_kcal + protein_kcal + fat_kcal
    if total == 0:
        return empty
    return {
        "carb": _quantize(carb_kcal * Decimal(100) / total),
        "protein": _quantize(protein_kcal * Decimal(100) / total),
        "fat": _quantize(fat_kcal * Decimal(100) / total),
    }


def _explain(report: dict[str, object], chunks: list[dict[str, object]]) -> tuple[str, list[str]]:
    fallback = _template(report, bool(chunks))
    chunk_ids = [str(chunk["chunk_id"]) for chunk in chunks if chunk.get("chunk_id")]
    payload = {
        "report": report,
        "chunks": [
            {"chunk_id": chunk.get("chunk_id"), "page": chunk.get("page"), "text": chunk.get("text")}
            for chunk in chunks
        ],
    }
    try:
        raw = generate(
            [
                {"role": "system", "content": REPORT_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            purpose="recommend",
        )
        parsed = _parse_json(raw)
    except Exception:  # noqa: BLE001
        return fallback, chunk_ids
    if parsed is None:
        return fallback, chunk_ids
    summary = str(parsed.get("summary") or "").strip()
    citations = parsed.get("citation_ids")
    if not summary or not isinstance(citations, list):
        return fallback, chunk_ids
    citation_text = [str(item) for item in citations]
    if any(item not in chunk_ids for item in citation_text):
        return fallback, chunk_ids
    if _PERCENT_RANGE.search(summary):
        return fallback, chunk_ids
    if not _numbers_allowed(summary, _allowed_numbers(payload)):
        return fallback, chunk_ids
    return summary, citation_text


def _template(report: dict[str, object], has_chunks: bool) -> str:
    hints = report.get("hints")
    if not isinstance(hints, list):
        text = "暂时无法整理这份报告。"
    else:
        text = "".join(str(item.get("message") or "") for item in hints if isinstance(item, dict))
    if has_chunks:
        text += "依据见检索片段。"
    return text


def _allowed_numbers(payload: dict[str, object]) -> set[str]:
    found: set[str] = set()
    _walk_numbers(payload, found)
    return found


def _walk_numbers(value: object, found: set[str]) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float, Decimal)):
        found.update(_forms(value))
        return
    if isinstance(value, dict):
        for item in value.values():
            _walk_numbers(item, found)
        return
    if isinstance(value, list):
        for item in value:
            _walk_numbers(item, found)
        return
    if isinstance(value, date):
        return


def _forms(value: float | Decimal) -> set[str]:
    quantized = Decimal(str(value)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    text = format(quantized, "f")
    short = text.rstrip("0").rstrip(".")
    return {text, short}


def _numbers_allowed(summary: str, allowed: set[str]) -> bool:
    for match in _NUMBER.findall(summary):
        forms = _forms(Decimal(match))
        if forms.isdisjoint(allowed):
            return False
    return True


def _parse_json(raw: str) -> dict[str, object] | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _retrieve(question: str) -> tuple[str, list[dict[str, object]]]:
    try:
        collection = get_collection(open_client(str(chroma_directory())))
        hits = search_guidelines(question, collection, embed_texts, limit=4)
    except Exception:  # noqa: BLE001
        return "down", []
    return "up", [
        {"chunk_id": hit.chunk_id, "source": hit.source, "page": hit.page, "text": hit.text}
        for hit in hits
    ]


def _item_payload(item: dict[str, object]) -> dict[str, object]:
    return {
        "meal_plan_id": item["meal_plan_id"],
        "recipe_id": item["recipe_id"],
        "name": item["name"],
        "meal_type": item["meal_type"],
        "servings": _number(item["servings"]) if isinstance(item["servings"], Decimal) else item["servings"],
        "kcal": _number(item["kcal"]) if isinstance(item["kcal"], Decimal) else item["kcal"],
        "carb_g": _number(item["carb_g"]) if isinstance(item["carb_g"], Decimal) else item["carb_g"],
        "protein_g": _number(item["protein_g"]) if isinstance(item["protein_g"], Decimal) else item["protein_g"],
        "fat_g": _number(item["fat_g"]) if isinstance(item["fat_g"], Decimal) else item["fat_g"],
        "fiber_g": _number(item["fiber_g"]) if isinstance(item["fiber_g"], Decimal) else item["fiber_g"],
        "sodium_mg": _number(item["sodium_mg"]) if isinstance(item["sodium_mg"], Decimal) else item["sodium_mg"],
        "oil_estimated": item["oil_estimated"],
        "gi_band_label": item["gi_band_label"],
        "gi_band_source": item["gi_band_source"],
        "gl_estimate": _number(item["gl_estimate"])
        if isinstance(item["gl_estimate"], Decimal)
        else item["gl_estimate"],
        "gl_is_approximate": True,
    }


def _sum(values: Iterable[object]) -> Decimal | None:
    numbers: list[Decimal] = []
    seen = False
    for value in values:
        seen = True
        if value is None:
            return None
        numbers.append(value if isinstance(value, Decimal) else Decimal(str(value)))
    if not seen:
        return None
    return _quantize(sum(numbers, Decimal(0)))


def _times(value: Decimal | None, factor: Decimal) -> Decimal | None:
    if value is None:
        return None
    return value * factor


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _show(value: Decimal | None) -> str:
    if value is None:
        return "—"
    text = format(_quantize(value), "f")
    return text.rstrip("0").rstrip(".")


def _rank(meal_type: str) -> int:
    try:
        return MEAL_TYPES.index(meal_type)
    except ValueError:
        return len(MEAL_TYPES)
