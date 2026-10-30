"""图谱邻居不携带营养数字。点击食材后才从成分表读取。"""

import json
from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import Neo4jError

from app.db.session import get_session
from app.graph.queries import neighborhood
from app.main import app
from app.services.graph import read_food_facts, read_neighbors


def test_neighborhood_returns_relations_without_nutrients() -> None:
    driver = MagicMock()
    driver.execute_query.side_effect = [
        ([{"label": "Food", "name": "荞麦", "pg_id": 5}], None, None),
        (
            [
                {
                    "a_label": "Disease",
                    "a_name": "2型糖尿病",
                    "a_pg_id": None,
                    "b_label": "Food",
                    "b_name": "荞麦",
                    "b_pg_id": 5,
                    "relation": "RECOMMEND",
                    "reason": "优选全谷物",
                    "citation": "指南第6页",
                }
            ],
            None,
            None,
        ),
    ]
    center, nodes, edges = neighborhood(driver, "荞麦", 2)
    assert center is not None
    assert center.pg_id == 5
    payload = {
        "nodes": [node.__dict__ for node in nodes],
        "links": [edge.__dict__ for edge in edges],
    }
    text = json.dumps(payload, ensure_ascii=False)
    assert "优选全谷物" in text
    assert "gi" not in text
    assert "kcal" not in text
    assert edges[0].source == "Disease:2型糖尿病"
    assert edges[0].target == "Food:荞麦"


def test_missing_name_returns_an_empty_graph() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)
    center, nodes, edges = neighborhood(driver, "没有这种", 1)
    assert center is None
    assert nodes == ()
    assert edges == ()
    assert driver.execute_query.call_count == 1


def test_neo4j_failure_marks_the_graph_down(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = MagicMock()
    monkeypatch.setattr("app.services.graph.neo4j_driver", lambda: driver)
    monkeypatch.setattr(
        "app.services.graph.neighborhood",
        lambda *_args: (_ for _ in ()).throw(Neo4jError("down")),
    )
    result = read_neighbors("荞麦", 1)
    assert result["graph"] == "down"
    assert result["nodes"] == []
    text = json.dumps(result, ensure_ascii=False)
    assert "gi" not in text
    assert "kcal" not in text
    driver.close.assert_called_once()


def test_food_facts_keep_a_null_gi(monkeypatch: pytest.MonkeyPatch) -> None:
    food = SimpleNamespace(
        id=5,
        name="荞麦",
        category="谷类",
        per_g=Decimal(100),
        kcal=Decimal(335),
        carb_g=Decimal(73),
        protein_g=Decimal(9),
        fat_g=None,
        fiber_g=None,
        sodium_mg=None,
        gi=None,
        gi_source=None,
        nutrient_source="成分表",
    )
    monkeypatch.setattr("app.services.graph.get_food", lambda _session, _pg_id: food)
    facts = read_food_facts(MagicMock(), 5)
    assert facts["gi"] is None
    assert facts["fat_g"] is None
    assert facts["gi_source"] == "待核对"
    assert facts["kcal"] == 335.0
    assert facts["nutrient_source"] == "成分表"


@pytest.fixture
def client() -> Iterator[TestClient]:
    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_graph_requires_token(client: TestClient) -> None:
    neighbors_response = client.get("/api/v1/graph/neighbors", params={"name": "荞麦"})
    facts = client.get("/api/v1/graph/foods/5")
    assert neighbors_response.status_code == 401
    assert facts.status_code == 401
    assert neighbors_response.json()["code"] == "unauthorized"
