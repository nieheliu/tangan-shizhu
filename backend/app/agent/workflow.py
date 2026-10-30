"""推荐工作流。七个节点都是函数，顺序固定，不会改调本机对话模型。"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agent.prompts import RECOMMEND_SYSTEM
from app.core.llm import generate
from app.rules.engine import RulesError, evaluate
from app.services.recipe_nutrition import (
    IngredientLine,
    OilNutrients,
    RecipeNutrition,
    calculate_recipe_nutrition,
)
from app.services.scoring import RESULT_LIMIT, STRICT_MINIMUM, recipe_score

GraphFoods = Callable[[list[str]], tuple[str, set[int]]]
Retriever = Callable[[str], tuple[str, list[dict[str, object]]]]
ProfileLoader = Callable[[int], dict[str, object]]
InventoryLoader = Callable[[int], list["StockItem"]]
RecipeLoader = Callable[[], list["RecipeCandidate"]]


class RecommendError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


@dataclass(frozen=True)
class StockItem:
    food_id: int
    name: str
    expiring: bool


@dataclass(frozen=True)
class RecipeCandidate:
    recipe_id: int
    name: str
    meal_types: tuple[str, ...]
    cooking_method: str | None
    servings: Decimal
    ingredients: tuple[IngredientLine, ...]
    aliases: tuple[tuple[int, tuple[str, ...]], ...] = ()


@dataclass
class ScoredRecipe:
    candidate: RecipeCandidate
    nutrition: RecipeNutrition
    rule_delta: int
    score: int
    missing_foods: tuple[str, ...]
    held_foods: tuple[str, ...]
    rule_messages: tuple[str, ...]
    reason: str = ""
    citation_ids: tuple[str, ...] = ()
    from_model: bool = False


@dataclass
class RecommendDeps:
    load_profile: ProfileLoader
    load_inventory: InventoryLoader
    load_recipes: RecipeLoader
    graph_foods: GraphFoods
    retrieve: Retriever
    oil_table: dict[str, tuple[Decimal | None, str]] = field(default_factory=dict)
    default_oil: OilNutrients | None = None
    food_catalog: frozenset[str] = frozenset()


class RecommendState(TypedDict, total=False):
    user_id: int
    meal_type: str | None
    only_inventory: bool
    exclude_ids: list[int]
    profile: dict[str, object]
    age: int | None
    inventory: list[StockItem]
    candidates: list[RecipeCandidate]
    blocked: bool
    block_message: str | None
    passed: list[ScoredRecipe]
    rejected: list[dict[str, object]]
    graph_status: str
    recommended_ids: set[int]
    chunks: list[dict[str, object]]
    rag_status: str
    response: dict[str, object]


def run_recommend(
    deps: RecommendDeps,
    *,
    user_id: int,
    meal_type: str | None,
    only_inventory: bool,
    exclude_ids: list[int],
) -> dict[str, object]:
    compiled = _compile(deps)
    final = compiled.invoke(
        {
            "user_id": user_id,
            "meal_type": meal_type,
            "only_inventory": only_inventory,
            "exclude_ids": exclude_ids,
            "blocked": False,
        }
    )
    response = final.get("response")
    if not isinstance(response, dict):
        raise RecommendError(status_code=500, detail="推荐没有完成", code="recommend_failed")
    return response


def _compile(deps: RecommendDeps) -> Any:
    graph = StateGraph(RecommendState)
    graph.add_node("load_profile", lambda state: _load_profile(state, deps))
    graph.add_node("load_inventory", lambda state: _load_inventory(state, deps))
    graph.add_node("rule_filter", lambda state: _rule_filter(state, deps))
    graph.add_node("graph_match", lambda state: _graph_match(state, deps))
    graph.add_node("rag_retrieve", lambda state: _rag_retrieve(state, deps))
    graph.add_node("llm_explain", lambda state: _llm_explain(state, deps))
    graph.add_node("post_validate", lambda state: _post_validate(state, deps))
    graph.set_entry_point("load_profile")
    graph.add_conditional_edges(
        "load_profile",
        lambda state: "stop" if state.get("blocked") else "continue",
        {"stop": "post_validate", "continue": "load_inventory"},
    )
    graph.add_edge("load_inventory", "rule_filter")
    graph.add_edge("rule_filter", "graph_match")
    graph.add_edge("graph_match", "rag_retrieve")
    graph.add_edge("rag_retrieve", "llm_explain")
    graph.add_edge("llm_explain", "post_validate")
    graph.add_edge("post_validate", END)
    return graph.compile()


def _load_profile(state: RecommendState, deps: RecommendDeps) -> dict[str, object]:
    profile = deps.load_profile(state["user_id"])
    diseases = [str(item) for item in profile.get("diseases") or []]
    age = profile.get("age")
    age_value = int(age) if isinstance(age, int) else None
    outcome = evaluate({"diseases": diseases}, age=age_value)
    if outcome.blocked:
        return {
            "profile": profile,
            "age": age_value,
            "blocked": True,
            "block_message": outcome.block_message,
            "passed": [],
            "rejected": [],
        }
    return {"profile": profile, "age": age_value, "blocked": False}


def _load_inventory(state: RecommendState, deps: RecommendDeps) -> dict[str, object]:
    inventory = deps.load_inventory(state["user_id"])
    excluded = set(state.get("exclude_ids") or [])
    meal = state.get("meal_type")
    candidates = []
    for recipe in deps.load_recipes():
        if recipe.recipe_id in excluded:
            continue
        if meal and meal not in recipe.meal_types:
            continue
        candidates.append(recipe)
    return {"inventory": inventory, "candidates": candidates}


def _rule_filter(state: RecommendState, deps: RecommendDeps) -> dict[str, object]:
    profile = state["profile"]
    diseases = [str(item) for item in profile.get("diseases") or []]
    allergies = [str(item) for item in profile.get("allergies") or []]
    dislikes = [str(item) for item in profile.get("dislikes") or []]
    stock = {item.food_id: item for item in state.get("inventory") or []}
    passed: list[ScoredRecipe] = []
    rejected: list[dict[str, object]] = []
    for recipe in state.get("candidates") or []:
        nutrition = calculate_recipe_nutrition(
            recipe.ingredients,
            servings=recipe.servings,
            cooking_method=recipe.cooking_method,
            oil_table=deps.oil_table,
            default_oil=deps.default_oil,
        )
        names = _food_names(recipe)
        context = {
            "kcal": nutrition.kcal,
            "carb_g": nutrition.carb_g,
            "protein_g": nutrition.protein_g,
            "fat_g": nutrition.fat_g,
            "fiber_g": nutrition.fiber_g,
            "sodium_mg": nutrition.sodium_mg,
            "main_staple_gi": nutrition.main_staple_gi,
            "main_staple_name": nutrition.main_staple_name or "",
            "food_ids": [item.food_id for item in recipe.ingredients],
            "food_names": names,
            "allergen_hit": _hit_count(recipe, allergies) > 0,
            "dislike_count": _hit_count(recipe, dislikes),
            "diseases": diseases,
        }
        outcome = evaluate(context, age=state.get("age"))
        if outcome.blocked:
            return {
                "blocked": True,
                "block_message": outcome.block_message,
                "passed": [],
                "rejected": rejected,
            }
        if outcome.rejected:
            rejected.append(
                {
                    "recipe_id": recipe.recipe_id,
                    "name": recipe.name,
                    "reasons": [
                        {
                            "rule_id": hit.rule_id,
                            "message": hit.message,
                            "source": hit.source,
                        }
                        for hit in outcome.hits
                        if hit.type == "reject"
                    ],
                }
            )
            continue
        missing = tuple(
            item.name for item in recipe.ingredients if item.food_id not in stock
        )
        held = tuple(item.name for item in recipe.ingredients if item.food_id in stock)
        messages = tuple(hit.message for hit in outcome.hits)
        scored = ScoredRecipe(
            candidate=recipe,
            nutrition=nutrition,
            rule_delta=outcome.delta,
            score=0,
            missing_foods=missing,
            held_foods=held,
            rule_messages=messages,
        )
        scored.score = _score_later(scored, stock, set())
        passed.append(scored)
    return {"passed": passed, "rejected": rejected}


def _graph_match(state: RecommendState, deps: RecommendDeps) -> dict[str, object]:
    diseases = [str(item) for item in (state.get("profile") or {}).get("diseases") or []]
    try:
        status, recommended = deps.graph_foods(diseases)
    except RulesError:
        raise
    except Exception:  # noqa: BLE001
        status, recommended = "down", set()
    stock = {item.food_id: item for item in state.get("inventory") or []}
    ranked: list[ScoredRecipe] = []
    for item in state.get("passed") or []:
        item.score = _score_later(item, stock, recommended if status == "up" else set())
        ranked.append(item)
    ranked.sort(key=lambda item: (-item.score, item.candidate.recipe_id))
    return {"passed": ranked, "graph_status": status, "recommended_ids": recommended}


def _rag_retrieve(state: RecommendState, deps: RecommendDeps) -> dict[str, object]:
    diseases = "、".join(
        str(item) for item in (state.get("profile") or {}).get("diseases") or []
    )
    meal = state.get("meal_type") or "日常"
    question = f"{diseases} {meal} 主食怎么吃".strip()
    try:
        status, chunks = deps.retrieve(question)
    except RulesError:
        raise
    except Exception:  # noqa: BLE001
        status, chunks = "down", []
    return {"rag_status": status, "chunks": chunks}


def _llm_explain(state: RecommendState, _deps: RecommendDeps) -> dict[str, object]:
    chunks = state.get("chunks") or []
    chunk_ids = [str(chunk["chunk_id"]) for chunk in chunks if chunk.get("chunk_id")]
    for item in state.get("passed") or []:
        reason, citations, from_model = _explain_one(item, chunks, chunk_ids)
        item.reason = reason
        item.citation_ids = tuple(citations)
        item.from_model = from_model
    return {"passed": state.get("passed") or []}


def _post_validate(state: RecommendState, deps: RecommendDeps) -> dict[str, object]:
    if state.get("blocked"):
        return {
            "response": _response(
                graph=state.get("graph_status") or "down",
                rag=state.get("rag_status") or "down",
                blocked=True,
                block_message=state.get("block_message"),
                strict=[],
                relaxed=[],
                rejected=state.get("rejected") or [],
            )
        }
    ordered = [
        str(chunk["chunk_id"])
        for chunk in state.get("chunks") or []
        if chunk.get("chunk_id")
    ]
    catalog = set(deps.food_catalog)
    ready: list[ScoredRecipe] = []
    for item in state.get("passed") or []:
        names = set(_food_names(item.candidate))
        citations = [cid for cid in item.citation_ids if cid in set(ordered)]
        invalid_citation = item.from_model and len(citations) != len(item.citation_ids)
        foreign = item.from_model and _mentions_other_food(item.reason, names, catalog)
        if not item.from_model or invalid_citation or foreign:
            item.reason = _template(item, bool(ordered))
            item.citation_ids = tuple(ordered)
        else:
            item.citation_ids = tuple(citations)
        ready.append(item)
    strict, relaxed = _split(ready, bool(state.get("only_inventory")))
    return {
        "response": _response(
            graph=state.get("graph_status") or "down",
            rag=state.get("rag_status") or "down",
            blocked=False,
            block_message=None,
            strict=[_item_payload(item) for item in strict],
            relaxed=[_item_payload(item) for item in relaxed],
            rejected=state.get("rejected") or [],
        )
    }


def _explain_one(
    item: ScoredRecipe,
    chunks: list[dict[str, object]],
    chunk_ids: list[str],
) -> tuple[str, list[str], bool]:
    payload = {
        "recipe_id": item.candidate.recipe_id,
        "name": item.candidate.name,
        "food_names": _food_names(item.candidate),
        "rule_messages": list(item.rule_messages),
        "chunks": [
            {"chunk_id": chunk.get("chunk_id"), "page": chunk.get("page"), "text": chunk.get("text")}
            for chunk in chunks
        ],
    }
    try:
        raw = generate(
            [
                {"role": "system", "content": RECOMMEND_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            purpose="recommend",
        )
        parsed = _parse_json(raw)
    except Exception:  # noqa: BLE001
        return _template(item, bool(chunks)), chunk_ids, False
    if parsed is None or str(parsed.get("recipe_id")) != str(item.candidate.recipe_id):
        return _template(item, bool(chunks)), chunk_ids, False
    reason = str(parsed.get("reason") or "").strip()
    citations = parsed.get("citation_ids")
    if not reason or not isinstance(citations, list):
        return _template(item, bool(chunks)), chunk_ids, False
    return reason, [str(cid) for cid in citations], True


def _score_later(item: ScoredRecipe, stock: dict[int, StockItem], recommended: set[int]) -> int:
    hits = [line for line in item.candidate.ingredients if line.food_id in stock]
    expiring = [line for line in hits if stock[line.food_id].expiring]
    relations = [line for line in item.candidate.ingredients if line.food_id in recommended]
    return recipe_score(
        inventory_hits=len(hits),
        expiring_hits=len(expiring),
        graph_relations=len(relations),
        missing_foods=len(item.missing_foods),
        rule_delta=item.rule_delta,
    )


def _split(items: list[ScoredRecipe], only_inventory: bool) -> tuple[list[ScoredRecipe], list[ScoredRecipe]]:
    if not only_inventory:
        return items[:RESULT_LIMIT], []
    strict = [item for item in items if not item.missing_foods]
    if len(strict) >= STRICT_MINIMUM:
        return strict[:RESULT_LIMIT], []
    relaxed = [item for item in items if item.missing_foods]
    return strict[:RESULT_LIMIT], relaxed[:RESULT_LIMIT]


def _template(item: ScoredRecipe, has_chunks: bool) -> str:
    held = "、".join(item.held_foods) if item.held_foods else "无"
    label = item.nutrition.gi_band_label or "空"
    reason = f"推荐理由：含库存食材 {held}；主食 GI 分级为{label}"
    if has_chunks:
        reason += "；依据见检索片段"
    return reason


def _mentions_other_food(reason: str, allowed: set[str], catalog: set[str]) -> bool:
    covered = reason
    for name in sorted(allowed, key=len, reverse=True):
        if len(name) >= 2:
            covered = covered.replace(name, " ")
    others = [name for name in catalog if name not in allowed and len(name) >= 2]
    return any(name in covered for name in others)


def _food_names(recipe: RecipeCandidate) -> list[str]:
    return [item.name for item in recipe.ingredients]


def _alias_map(recipe: RecipeCandidate) -> dict[int, tuple[str, ...]]:
    return dict(recipe.aliases)


def _hit_count(recipe: RecipeCandidate, needles: list[str]) -> int:
    aliases = _alias_map(recipe)
    count = 0
    for ingredient in recipe.ingredients:
        names = [ingredient.name, *aliases.get(ingredient.food_id, ())]
        if any(_matches(needle, names) for needle in needles):
            count += 1
    return count


def _matches(needle: str, names: list[str]) -> bool:
    token = needle.strip()
    if not token:
        return False
    return any(token == name or token in name for name in names)


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


def _item_payload(item: ScoredRecipe) -> dict[str, object]:
    nutrition = item.nutrition
    return {
        "recipe_id": item.candidate.recipe_id,
        "name": item.candidate.name,
        "score": item.score,
        "reason": item.reason,
        "citation_ids": list(item.citation_ids),
        "missing_foods": list(item.missing_foods),
        "kcal": _number(nutrition.kcal),
        "carb_g": _number(nutrition.carb_g),
        "protein_g": _number(nutrition.protein_g),
        "fat_g": _number(nutrition.fat_g),
        "fiber_g": _number(nutrition.fiber_g),
        "sodium_mg": _number(nutrition.sodium_mg),
        "oil_estimated": nutrition.oil_estimated,
        "main_staple_gi": _number(nutrition.main_staple_gi),
        "gi_band": nutrition.gi_band,
        "gi_band_label": nutrition.gi_band_label,
        "gi_band_source": nutrition.gi_band_source,
        "gl_estimate": _number(nutrition.gl_estimate),
        "gl_is_approximate": nutrition.gl_is_approximate,
    }


def _response(
    *,
    graph: str,
    rag: str,
    blocked: bool,
    block_message: str | None,
    strict: list[dict[str, object]],
    relaxed: list[dict[str, object]],
    rejected: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "graph": graph,
        "rag": rag,
        "blocked": blocked,
        "block_message": block_message,
        "strict": strict,
        "relaxed": relaxed,
        "rejected": rejected,
    }


def _number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
