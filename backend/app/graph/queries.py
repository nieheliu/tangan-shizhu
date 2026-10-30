"""图谱查询。返回关系和编号，不返回 GI 或营养素含量。"""

from dataclasses import dataclass

from neo4j import Driver, RoutingControl


class GraphQueryError(Exception):
    """查询没有执行成功。"""


@dataclass(frozen=True)
class FoodHit:
    name: str
    pg_id: int | None
    reason: str | None
    source: str | None


@dataclass(frozen=True)
class NutrientLimit:
    name: str
    max_per_day: int | None
    unit: str | None
    reason: str | None
    source: str | None


@dataclass(frozen=True)
class MethodHit:
    name: str
    reason: str | None
    source: str | None


@dataclass(frozen=True)
class DiseaseGuidance:
    disease: str
    recommended: tuple[FoodHit, ...]
    avoided: tuple[FoodHit, ...]
    limits: tuple[NutrientLimit, ...]
    avoided_methods: tuple[MethodHit, ...]


@dataclass(frozen=True)
class GraphLink:
    relation: str
    direction: str
    other_label: str
    other_name: str
    other_pg_id: int | None
    reason: str | None
    source: str | None


@dataclass(frozen=True)
class RecipeMatch:
    name: str
    pg_id: int
    overlap: int


def disease_guidance(driver: Driver, disease: str) -> DiseaseGuidance:
    return DiseaseGuidance(
        disease=disease,
        recommended=_foods(driver, disease, "RECOMMEND"),
        avoided=_foods(driver, disease, "AVOID"),
        limits=_limits(driver, disease),
        avoided_methods=_methods(driver, disease),
    )


def food_relations(driver: Driver, name: str) -> tuple[GraphLink, ...]:
    records, _, _ = driver.execute_query(
        """
        MATCH (f:Food {name: $name})-[rel]-(other)
        RETURN type(rel) AS relation,
               startNode(rel) = f AS outgoing,
               labels(other)[0] AS other_label,
               other.name AS other_name,
               other.pg_id AS other_pg_id,
               rel.reason AS reason,
               rel.source AS source
        ORDER BY relation, other_name
        """,
        parameters_={"name": name},
        routing_=RoutingControl.READ,
    )
    return tuple(
        GraphLink(
            relation=record["relation"],
            direction="out" if record["outgoing"] else "in",
            other_label=record["other_label"],
            other_name=record["other_name"],
            other_pg_id=record["other_pg_id"],
            reason=record["reason"],
            source=record["source"],
        )
        for record in records
    )


def match_recipes(
    driver: Driver,
    food_pg_ids: list[int],
    *,
    limit: int = 20,
) -> tuple[RecipeMatch, ...]:
    if not food_pg_ids:
        return ()
    records, _, _ = driver.execute_query(
        """
        MATCH (recipe:Recipe)-[:CONTAINS]->(food:Food)
        WHERE food.pg_id IN $ids
        RETURN recipe.name AS name, recipe.pg_id AS pg_id, count(food) AS overlap
        ORDER BY overlap DESC, recipe.name
        LIMIT $limit
        """,
        parameters_={"ids": food_pg_ids, "limit": limit},
        routing_=RoutingControl.READ,
    )
    return tuple(
        RecipeMatch(
            name=record["name"],
            pg_id=record["pg_id"],
            overlap=record["overlap"],
        )
        for record in records
    )


_FOOD_RELATION = {
    "RECOMMEND": """
        MATCH (d:Disease {name: $disease})-[rel:RECOMMEND]->(food:Food)
        RETURN food.name AS name, food.pg_id AS pg_id,
               rel.reason AS reason, rel.source AS source
        ORDER BY food.name
    """,
    "AVOID": """
        MATCH (d:Disease {name: $disease})-[rel:AVOID]->(food:Food)
        RETURN food.name AS name, food.pg_id AS pg_id,
               rel.reason AS reason, rel.source AS source
        ORDER BY food.name
    """,
}


def _foods(driver: Driver, disease: str, relation: str) -> tuple[FoodHit, ...]:
    query = _FOOD_RELATION.get(relation)
    if query is None:
        raise GraphQueryError("只查询推荐或禁忌")
    records, _, _ = driver.execute_query(
        query,
        parameters_={"disease": disease},
        routing_=RoutingControl.READ,
    )
    return tuple(
        FoodHit(
            name=record["name"],
            pg_id=record["pg_id"],
            reason=record["reason"],
            source=record["source"],
        )
        for record in records
    )


def _limits(driver: Driver, disease: str) -> tuple[NutrientLimit, ...]:
    records, _, _ = driver.execute_query(
        """
        MATCH (d:Disease {name: $disease})-[rel:LIMIT]->(nutrient:Nutrient)
        RETURN nutrient.name AS name, rel.max_per_day AS max_per_day,
               rel.unit AS unit, rel.reason AS reason, rel.source AS source
        ORDER BY nutrient.name
        """,
        parameters_={"disease": disease},
        routing_=RoutingControl.READ,
    )
    return tuple(
        NutrientLimit(
            name=record["name"],
            max_per_day=record["max_per_day"],
            unit=record["unit"],
            reason=record["reason"],
            source=record["source"],
        )
        for record in records
    )


def _methods(driver: Driver, disease: str) -> tuple[MethodHit, ...]:
    records, _, _ = driver.execute_query(
        """
        MATCH (d:Disease {name: $disease})-[rel:AVOID_METHOD]->(method:CookingMethod)
        RETURN method.name AS name, rel.reason AS reason, rel.source AS source
        ORDER BY method.name
        """,
        parameters_={"disease": disease},
        routing_=RoutingControl.READ,
    )
    return tuple(
        MethodHit(name=record["name"], reason=record["reason"], source=record["source"])
        for record in records
    )
