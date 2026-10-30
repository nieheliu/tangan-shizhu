"""推荐流程。不连接数据库、图谱、向量库或云端模型。"""

import json
from collections.abc import Iterator
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.agent.workflow import (
    RecipeCandidate,
    RecommendDeps,
    StockItem,
    run_recommend,
)
from app.db.session import get_session
from app.main import app
from app.models.entities import RecommendLog, User
from app.rules.engine import RulesError
from app.services import auth as auth_service
from app.services.recipe_nutrition import IngredientLine
from app.services.recommend import RecommendDataError


def _line(
    food_id: int,
    name: str,
    *,
    gi: Decimal | None = Decimal(50),
    kcal: Decimal | None = Decimal(200),
    is_main: bool = True,
) -> IngredientLine:
    return IngredientLine(
        food_id=food_id,
        name=name,
        amount_g=Decimal(100),
        per_g=Decimal(100),
        is_main=is_main,
        is_oil=False,
        kcal=kcal,
        carb_g=Decimal(10),
        protein_g=Decimal(1),
        fat_g=Decimal(1),
        fiber_g=Decimal(0),
        sodium_mg=Decimal(0),
        gi=gi,
        gi_source="待核对",
    )


def _recipe(
    recipe_id: int,
    name: str,
    ingredients: list[IngredientLine],
    *,
    meals: tuple[str, ...] = ("午餐",),
) -> RecipeCandidate:
    return RecipeCandidate(
        recipe_id=recipe_id,
        name=name,
        meal_types=meals,
        cooking_method="煮",
        servings=Decimal(1),
        ingredients=tuple(ingredients),
    )


def _profile(**overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "diseases": ["2型糖尿病"],
        "allergies": [],
        "dislikes": [],
        "age": 36,
    }
    profile.update(overrides)
    return profile


def _deps(
    recipes: list[RecipeCandidate],
    *,
    profile: dict[str, object] | None = None,
    inventory: list[StockItem] | None = None,
    graph: object | None = None,
    retrieve: object | None = None,
    catalog: frozenset[str] = frozenset(),
) -> RecommendDeps:
    chosen = profile if profile is not None else _profile()
    stock = inventory if inventory is not None else []

    def load_profile(_user_id: int) -> dict[str, object]:
        return chosen

    def load_inventory(_user_id: int) -> list[StockItem]:
        return stock

    def load_recipes() -> list[RecipeCandidate]:
        return recipes

    def graph_foods(diseases: list[str]) -> tuple[str, set[int]]:
        if callable(graph):
            return graph(diseases)
        return "up", set()

    def retrieve_chunks(question: str) -> tuple[str, list[dict[str, object]]]:
        if callable(retrieve):
            return retrieve(question)
        return "up", []

    return RecommendDeps(
        load_profile=load_profile,
        load_inventory=load_inventory,
        load_recipes=load_recipes,
        graph_foods=graph_foods,
        retrieve=retrieve_chunks,
        oil_table={},
        food_catalog=catalog,
    )


def _silence_llm(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def cloud(_settings: object) -> None:
        raise TimeoutError("cloud")

    def local(_settings: object) -> None:
        calls.append("ollama")
        raise AssertionError("不应该调用本机对话模型")

    monkeypatch.setattr("app.core.llm.cloud_client", cloud)
    monkeypatch.setattr("app.core.llm.ollama_client", local)
    return calls


def _run(
    deps: RecommendDeps,
    *,
    meal_type: str | None = None,
    only_inventory: bool = False,
    exclude_ids: list[int] | None = None,
) -> dict[str, object]:
    return run_recommend(
        deps,
        user_id=1,
        meal_type=meal_type,
        only_inventory=only_inventory,
        exclude_ids=exclude_ids or [],
    )


def test_allergen_and_high_gi_are_rejected_dislike_only_lowers_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _silence_llm(monkeypatch)
    oats = _recipe(1, "燕麦粥", [_line(1, "燕麦")])
    shrimp = _recipe(2, "虾仁炒蛋", [_line(2, "虾仁", gi=Decimal(50))])
    rice = _recipe(3, "白米饭", [_line(3, "大米", gi=Decimal(70))])
    herb = _recipe(4, "香菜汤", [_line(4, "香菜")])
    result = _run(
        _deps(
            [oats, shrimp, rice, herb],
            profile=_profile(allergies=["虾"], dislikes=["香菜"]),
            inventory=[
                StockItem(1, "燕麦", False),
                StockItem(2, "虾仁", False),
                StockItem(3, "大米", False),
                StockItem(4, "香菜", False),
            ],
        )
    )
    strict = result["strict"]
    assert isinstance(strict, list)
    ids = [item["recipe_id"] for item in strict]
    assert ids == [1, 4]
    assert strict[0]["score"] == strict[1]["score"] + 1
    rejected = {item["recipe_id"]: item for item in result["rejected"]}
    assert rejected[2]["reasons"][0]["rule_id"] == "COMMON-001"
    assert rejected[3]["reasons"][0]["rule_id"] == "DM-001"
    assert result["relaxed"] == []


def test_cloud_failure_uses_template_and_skips_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _silence_llm(monkeypatch)
    result = _run(
        _deps(
            [_recipe(1, "燕麦粥", [_line(1, "燕麦")])],
            inventory=[StockItem(1, "燕麦", False)],
            retrieve=lambda _question: (
                "up",
                [{"chunk_id": "guide:1:0", "page": 1, "text": "主食要定量"}],
            ),
        )
    )
    item = result["strict"][0]
    assert item["reason"] == "推荐理由：含库存食材 燕麦；主食 GI 分级为低；依据见检索片段"
    assert item["citation_ids"] == ["guide:1:0"]
    assert calls == []


def test_graph_down_keeps_recipes_without_graph_bonus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _silence_llm(monkeypatch)

    def graph_down(_diseases: list[str]) -> tuple[str, set[int]]:
        raise RuntimeError("neo4j")

    result = _run(
        _deps(
            [_recipe(1, "燕麦粥", [_line(5, "燕麦")])],
            inventory=[StockItem(5, "燕麦", False)],
            graph=graph_down,
        )
    )
    assert result["graph"] == "down"
    assert result["strict"][0]["recipe_id"] == 1
    assert result["strict"][0]["score"] == 2


def test_graph_relation_adds_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    _silence_llm(monkeypatch)
    result = _run(
        _deps(
            [_recipe(1, "燕麦粥", [_line(5, "燕麦")])],
            inventory=[StockItem(5, "燕麦", False)],
            graph=lambda _diseases: ("up", {5}),
        )
    )
    assert result["graph"] == "up"
    assert result["strict"][0]["score"] == 4


def test_rag_down_omits_guideline_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    _silence_llm(monkeypatch)

    def rag_down(_question: str) -> tuple[str, list[dict[str, object]]]:
        raise RuntimeError("chroma")

    result = _run(
        _deps(
            [_recipe(1, "燕麦粥", [_line(1, "燕麦")])],
            inventory=[StockItem(1, "燕麦", False)],
            retrieve=rag_down,
        )
    )
    assert result["rag"] == "down"
    item = result["strict"][0]
    assert "依据见检索片段" not in item["reason"]
    assert item["citation_ids"] == []
    assert "第" not in item["reason"]


def test_only_inventory_splits_when_strict_is_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _silence_llm(monkeypatch)
    held = _recipe(1, "燕麦粥", [_line(1, "燕麦")])
    missing = _recipe(2, "荞麦饭", [_line(2, "荞麦")])
    result = _run(
        _deps([held, missing], inventory=[StockItem(1, "燕麦", False)]),
        only_inventory=True,
    )
    strict_ids = [item["recipe_id"] for item in result["strict"]]
    relaxed_ids = [item["recipe_id"] for item in result["relaxed"]]
    assert strict_ids == [1]
    assert relaxed_ids == [2]
    assert 1 not in relaxed_ids
    assert result["relaxed"][0]["missing_foods"] == ["荞麦"]


def test_backend_nutrition_ignores_model_kcal(monkeypatch: pytest.MonkeyPatch) -> None:
    def generate(messages: list[dict[str, str]], *, purpose: str) -> str:
        assert purpose == "recommend"
        payload = json.loads(messages[1]["content"])
        return json.dumps(
            {
                "recipe_id": payload["recipe_id"],
                "reason": "燕麦适合",
                "citation_ids": ["c1"],
                "kcal": 9999,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.agent.workflow.generate", generate)
    result = _run(
        _deps(
            [_recipe(1, "燕麦粥", [_line(1, "燕麦")])],
            inventory=[StockItem(1, "燕麦", False)],
            retrieve=lambda _question: ("up", [{"chunk_id": "c1", "page": 1, "text": "主食"}]),
            catalog=frozenset({"燕麦", "香菜"}),
        )
    )
    item = result["strict"][0]
    assert item["kcal"] == 200.0
    assert item["reason"] == "燕麦适合"
    assert item["gl_is_approximate"] is True
    assert item["gi_band_source"] == "待核对"


def test_invalid_citation_or_foreign_food_falls_back_to_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def generate(messages: list[dict[str, str]], *, purpose: str) -> str:
        assert purpose == "recommend"
        payload = json.loads(messages[1]["content"])
        if payload["recipe_id"] == 1:
            return json.dumps(
                {"recipe_id": 1, "reason": "再加香菜", "citation_ids": ["c1"]},
                ensure_ascii=False,
            )
        return json.dumps(
            {"recipe_id": 2, "reason": "荞麦可以", "citation_ids": ["nope"]},
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.agent.workflow.generate", generate)
    result = _run(
        _deps(
            [
                _recipe(1, "燕麦粥", [_line(1, "燕麦")]),
                _recipe(2, "荞麦饭", [_line(2, "荞麦")]),
            ],
            inventory=[StockItem(1, "燕麦", False), StockItem(2, "荞麦", False)],
            retrieve=lambda _question: ("up", [{"chunk_id": "c1", "page": 1, "text": "主食"}]),
            catalog=frozenset({"燕麦", "荞麦", "香菜"}),
        )
    )
    by_id = {item["recipe_id"]: item for item in result["strict"]}
    assert by_id[1]["reason"].startswith("推荐理由：")
    assert "香菜" not in by_id[1]["reason"]
    assert by_id[2]["reason"].startswith("推荐理由：")
    assert "nope" not in by_id[2]["citation_ids"]
    assert by_id[2]["citation_ids"] == ["c1"]


def test_kidney_disease_blocks_without_calling_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def generate(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("拦截后不应调用模型")

    monkeypatch.setattr("app.agent.workflow.generate", generate)
    result = _run(
        _deps(
            [_recipe(1, "燕麦粥", [_line(1, "燕麦")])],
            profile=_profile(diseases=["肾病"]),
        )
    )
    assert result["blocked"] is True
    assert "请就医" in str(result["block_message"])
    assert result["strict"] == []
    assert result["relaxed"] == []


def test_rules_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise RulesError("规则文件损坏")

    monkeypatch.setattr("app.agent.workflow.evaluate", broken)
    with pytest.raises(RulesError):
        _run(_deps([_recipe(1, "燕麦粥", [_line(1, "燕麦")])]))


def test_missing_profile_propagates() -> None:
    def missing(_user_id: int) -> dict[str, object]:
        raise RecommendDataError(status_code=422, detail="请先填写健康档案", code="profile_missing")

    deps = _deps([])
    deps.load_profile = missing
    with pytest.raises(RecommendDataError) as caught:
        _run(deps)
    assert caught.value.code == "profile_missing"


def test_other_meal_and_excluded_id_are_not_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _silence_llm(monkeypatch)
    breakfast = _recipe(1, "燕麦粥", [_line(1, "燕麦")], meals=("早餐",))
    lunch = _recipe(2, "荞麦饭", [_line(2, "荞麦")])
    result = _run(
        _deps(
            [breakfast, lunch],
            inventory=[StockItem(1, "燕麦", False), StockItem(2, "荞麦", False)],
        ),
        meal_type="午餐",
        exclude_ids=[2],
    )
    assert result["strict"] == []
    assert result["rejected"] == []


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    users: dict[int, User] = {}

    def get_by_username(_session: object, username: str) -> User | None:
        return next((user for user in users.values() if user.username == username), None)

    def get_by_id(_session: object, user_id: int) -> User | None:
        return users.get(user_id)

    def add_user(_session: object, user: User) -> User:
        user.id = len(users) + 1
        users[user.id] = user
        return user

    monkeypatch.setattr(auth_service, "get_by_username", get_by_username)
    monkeypatch.setattr(auth_service, "add_user", add_user)
    monkeypatch.setattr("app.api.deps.get_by_id", get_by_id)

    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _token(client: TestClient) -> str:
    created = client.post(
        "/api/v1/auth/register",
        json={"username": "demo", "password": "secret"},
    )
    assert created.status_code == 200
    logged = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "secret"},
    )
    assert logged.status_code == 200
    return str(logged.json()["access_token"])


def test_recommend_requires_token(client: TestClient) -> None:
    response = client.post("/api/v1/recommend", json={})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_recommend_logs_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = MagicMock()

    def override_session() -> Iterator[MagicMock]:
        yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        "app.api.v1.recommend.recommend_for_user",
        lambda *_args, **_kwargs: {
            "graph": "down",
            "rag": "down",
            "blocked": False,
            "block_message": None,
            "strict": [],
            "relaxed": [],
            "rejected": [],
        },
    )
    token = _token(client)
    response = client.post(
        "/api/v1/recommend",
        json={"only_inventory": True, "exclude_ids": [3]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["strict"] == []
    saved = session.add.call_args.args[0]
    assert isinstance(saved, RecommendLog)
    assert saved.request["only_inventory"] is True
    assert saved.request["exclude_ids"] == [3]
    assert saved.rejected == []
    assert saved.latency_ms >= 0
    session.commit.assert_called_once()


def test_rules_error_is_api_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RulesError("规则文件损坏")

    monkeypatch.setattr("app.api.v1.recommend.recommend_for_user", broken)
    token = _token(client)
    response = client.post(
        "/api/v1/recommend",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "rules_unavailable"


def test_missing_profile_is_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RecommendDataError(
            status_code=422, detail="请先填写健康档案", code="profile_missing"
        )

    monkeypatch.setattr("app.api.v1.recommend.recommend_for_user", missing)
    token = _token(client)
    response = client.post(
        "/api/v1/recommend",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "profile_missing"
