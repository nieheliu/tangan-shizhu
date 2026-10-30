"""从数据库装载推荐所需的档案、库存和食谱。"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.workflow import (
    RecipeCandidate,
    RecommendDeps,
    StockItem,
    run_recommend,
)
from app.graph.queries import disease_guidance
from app.graph.sync import neo4j_driver
from app.models.entities import (
    Food,
    HealthProfile,
    Recipe,
    RecipeIngredient,
    RecommendLog,
)
from app.rag.embeddings import embed_texts
from app.rag.retrieve import search_guidelines
from app.rag.vectorstore import chroma_directory, get_collection, open_client
from app.repositories.profiles import get_by_user_id
from app.services.inventory import list_inventory
from app.services.nutrition import age_in_year, current_year
from app.services.recipe_nutrition import (
    IngredientLine,
    OilNutrients,
    is_cooking_oil,
    load_cooking_oil,
)

_DISEASE = "2型糖尿病"


class RecommendDataError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def recommend_for_user(
    session: Session,
    user_id: int,
    *,
    meal_type: str | None,
    only_inventory: bool,
    exclude_ids: list[int],
) -> dict[str, object]:
    return run_recommend(
        default_deps(session),
        user_id=user_id,
        meal_type=meal_type,
        only_inventory=only_inventory,
        exclude_ids=exclude_ids,
    )


def default_deps(session: Session) -> RecommendDeps:
    foods = list(session.scalars(select(Food)))
    by_id = {food.id: food for food in foods}
    oil = by_id.get(_oil_id(foods))
    return RecommendDeps(
        load_profile=lambda user_id: _profile(session, user_id),
        load_inventory=lambda user_id: _stock(session, user_id),
        load_recipes=lambda: _recipes(session, by_id),
        graph_foods=_graph_foods,
        retrieve=_retrieve,
        oil_table=load_cooking_oil(),
        default_oil=None
        if oil is None
        else OilNutrients(per_g=oil.per_g, kcal=oil.kcal, fat_g=oil.fat_g),
        food_catalog=frozenset(_catalog_names(foods)),
    )


def _profile(session: Session, user_id: int) -> dict[str, object]:
    profile = get_by_user_id(session, user_id)
    if profile is None:
        raise RecommendDataError(status_code=422, detail="请先填写健康档案", code="profile_missing")
    return {
        "diseases": list(profile.diseases or []),
        "allergies": list(profile.allergies or []),
        "dislikes": list(profile.dislikes or []),
        "age": _age(profile),
    }


def _age(profile: HealthProfile) -> int | None:
    if profile.birth_year is None:
        return None
    return age_in_year(profile.birth_year, current_year())


def _stock(session: Session, user_id: int) -> list[StockItem]:
    items: list[StockItem] = []
    for view in list_inventory(session, user_id):
        if view.status == "expired" or view.grams is None:
            continue
        items.append(
            StockItem(
                food_id=view.food_id,
                name=view.food_name,
                expiring=view.status == "expiring",
            )
        )
    return items


def _recipes(session: Session, foods: dict[int, Food]) -> list[RecipeCandidate]:
    recipes = list(session.scalars(select(Recipe).order_by(Recipe.id)))
    grouped: dict[int, list[RecipeIngredient]] = {}
    for row in session.scalars(select(RecipeIngredient)):
        grouped.setdefault(row.recipe_id, []).append(row)
    candidates: list[RecipeCandidate] = []
    for recipe in recipes:
        lines: list[IngredientLine] = []
        aliases: list[tuple[int, tuple[str, ...]]] = []
        for row in grouped.get(recipe.id, []):
            food = foods.get(row.food_id)
            if food is None:
                continue
            lines.append(_line(food, row))
            aliases.append((food.id, tuple(str(name) for name in food.alias or [])))
        candidates.append(
            RecipeCandidate(
                recipe_id=recipe.id,
                name=recipe.name,
                meal_types=tuple(str(item) for item in recipe.meal_types or []),
                cooking_method=recipe.cooking_method,
                servings=recipe.servings or Decimal(1),
                ingredients=tuple(lines),
                aliases=tuple(aliases),
            )
        )
    return candidates


def _line(food: Food, row: RecipeIngredient) -> IngredientLine:
    return IngredientLine(
        food_id=food.id,
        name=food.name,
        amount_g=row.amount_g,
        per_g=food.per_g or Decimal(100),
        is_main=row.is_main,
        is_oil=is_cooking_oil(food.category),
        kcal=food.kcal,
        carb_g=food.carb_g,
        protein_g=food.protein_g,
        fat_g=food.fat_g,
        fiber_g=food.fiber_g,
        sodium_mg=food.sodium_mg,
        gi=food.gi,
        gi_source=food.gi_source,
    )


def _catalog_names(foods: list[Food]) -> list[str]:
    names: list[str] = []
    for food in foods:
        if food.name:
            names.append(food.name)
        for alias in food.alias or []:
            text = str(alias).strip()
            if text:
                names.append(text)
    return names


def _oil_id(foods: list[Food]) -> int | None:
    for food in foods:
        if food.name == "花生油":
            return food.id
    return None


def _graph_foods(diseases: list[str]) -> tuple[str, set[int]]:
    if _DISEASE not in diseases:
        return "up", set()
    driver = neo4j_driver()
    try:
        guidance = disease_guidance(driver, _DISEASE)
    finally:
        driver.close()
    return "up", {item.pg_id for item in guidance.recommended if item.pg_id is not None}


def _retrieve(question: str) -> tuple[str, list[dict[str, object]]]:
    collection = get_collection(open_client(str(chroma_directory())))
    hits = search_guidelines(question, collection, embed_texts, limit=4)
    return "up", [
        {
            "chunk_id": hit.chunk_id,
            "source": hit.source,
            "page": hit.page,
            "text": hit.text,
        }
        for hit in hits
    ]


def save_recommend_log(
    session: Session,
    *,
    user_id: int,
    request: dict[str, object],
    result: dict[str, object],
    rejected: list[object],
    latency_ms: int,
) -> None:
    session.add(
        RecommendLog(
            user_id=user_id,
            request=request,
            result=result,
            rejected=rejected,
            latency_ms=latency_ms,
        )
    )
    session.commit()
