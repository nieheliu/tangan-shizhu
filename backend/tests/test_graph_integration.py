import pytest
from neo4j.exceptions import Neo4jError

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.graph.queries import disease_guidance, food_relations, match_recipes
from app.graph.sync import GraphUnavailable, build_graph, neo4j_driver

pytestmark = pytest.mark.integration

_BANNED = {"kcal", "carb_g", "protein_g", "fat_g", "fiber_g", "sodium_mg", "gi", "gi_source"}


def test_graph_has_cited_relations_and_no_nutrient_properties() -> None:
    settings = get_settings()
    if not settings.database_url or not settings.neo4j_uri or not settings.neo4j_password:
        pytest.skip("数据库或 Neo4j 未配置")
    driver = None
    try:
        driver = neo4j_driver()
        driver.verify_connectivity()
    except (OSError, Neo4jError, GraphUnavailable):
        if driver is not None:
            driver.close()
        pytest.skip("Neo4j 不可用")

    with get_sessionmaker()() as session:
        stats = build_graph(session, driver)
    assert stats["skipped"] == 0
    assert stats["relations"] == 33

    try:
        food = driver.execute_query(
            "MATCH (food:Food {name: $name}) RETURN keys(food) AS keys, food.pg_id AS pg_id",
            parameters_={"name": "燕麦"},
        )
        keys = set(food.records[0]["keys"])
        assert keys <= {"name", "category", "pg_id"}
        assert not keys & _BANNED
        oat_id = food.records[0]["pg_id"]
        assert isinstance(oat_id, int)

        edge = driver.execute_query(
            """
            MATCH (:Recipe {name: '燕麦粥'})-[rel:CONTAINS]->(:Food {name: '燕麦'})
            RETURN keys(rel) AS keys
            """
        )
        assert list(edge.records[0]["keys"]) == []

        guidance = disease_guidance(driver, "2型糖尿病")
        oats = next(item for item in guidance.recommended if item.name == "燕麦")
        assert oats.pg_id == oat_id
        assert "第6页" in (oats.source or "")
        drink = next(item for item in guidance.avoided if item.name == "含糖饮料")
        assert drink.pg_id is None
        limits = {item.name: item for item in guidance.limits}
        assert limits["烹调油"].max_per_day == 25
        assert limits["糖"].max_per_day is None
        assert {item.name for item in guidance.avoided_methods} == {"勾芡", "沾粉"}

        links = food_relations(driver, "燕麦")
        assert any(link.relation == "RECOMMEND" and link.other_name == "2型糖尿病" for link in links)
        assert any(link.relation == "SUBSTITUTE" and link.other_name == "大米" for link in links)
        matches = match_recipes(driver, [oat_id])
        assert any(item.name == "燕麦粥" and item.overlap == 1 for item in matches)
        assert match_recipes(driver, []) == ()

        labels = driver.execute_query("MATCH (n) RETURN DISTINCT labels(n)[0] AS label")
        assert {record["label"] for record in labels.records} >= {
            "Food",
            "Recipe",
            "Disease",
            "Nutrient",
            "CookingMethod",
        }
        types = driver.execute_query("MATCH ()-[rel]->() RETURN DISTINCT type(rel) AS type")
        assert {record["type"] for record in types.records} >= {
            "RECOMMEND",
            "AVOID",
            "LIMIT",
            "CONTAINS",
            "COOKED_BY",
            "AVOID_METHOD",
            "SUBSTITUTE",
        }
    finally:
        driver.close()
