"""营养报告。合计不用 0 填充，供能比不写未核对的目标区间。"""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.services.reports import (
    assemble_daily,
    assemble_weekly,
    daily_report,
    explain_report,
)


def _dish(**overrides: object) -> dict[str, object]:
    dish: dict[str, object] = {
        "meal_plan_id": 1,
        "recipe_id": 1,
        "name": "燕麦粥",
        "meal_type": "午餐",
        "servings": Decimal(1),
        "kcal": Decimal(100),
        "carb_g": Decimal(50),
        "protein_g": Decimal(10),
        "fat_g": Decimal(10),
        "fiber_g": Decimal(3),
        "sodium_mg": Decimal(1),
        "oil_estimated": False,
        "gi_band_label": None,
        "gi_band_source": "待核对",
        "gl_estimate": Decimal("5.5"),
    }
    dish.update(overrides)
    return dish


def test_ratios_and_target_comparison_do_not_invent_a_range() -> None:
    report = assemble_daily(date(2026, 10, 30), [_dish()], 1650, "待核对")
    assert report["totals"]["kcal"] == 100.0
    assert report["energy_ratios"]["carb"] == 60.61
    assert report["energy_ratios"]["protein"] == 12.12
    assert report["energy_ratios"]["fat"] == 27.27
    assert report["energy_ratios"]["target_range"] is None
    assert report["fiber_target_g"] is None
    assert report["fiber_met_days"] is None
    text = json.dumps(report, ensure_ascii=False, default=str)
    assert "低于每日目标 1650 kcal" in text
    assert "待核对" in text
    assert "45%" not in text
    assert "不显示区间" in text


def test_missing_nutrient_blocks_the_day_total() -> None:
    report = assemble_daily(
        date(2026, 10, 30),
        [_dish(), _dish(meal_plan_id=2, name="荞麦饭", kcal=None)],
        1650,
        "待核对",
    )
    assert report["totals"]["kcal"] is None
    assert report["meal_count"] == 2
    messages = " ".join(item["message"] for item in report["hints"])
    assert "缺少热量" in messages
    assert "低于" not in messages


def test_weekly_average_skips_days_without_kcal() -> None:
    end = date(2026, 10, 30)
    days = [
        assemble_daily(date(2026, 10, 28), [_dish(kcal=Decimal(100))], 1650, "待核对"),
        assemble_daily(date(2026, 10, 29), [], 1650, "待核对"),
        assemble_daily(date(2026, 10, 30), [_dish(kcal=Decimal(300))], 1650, "待核对"),
    ]
    report = assemble_weekly(end, days)
    assert report["kcal_average"] == 200.0
    assert report["days_with_kcal"] == 2
    assert report["fiber_met_days"] is None
    assert report["target_range"] is None
    assert report["days"][1]["kcal"] is None


def test_plan_servings_scale_nutrition(monkeypatch: pytest.MonkeyPatch) -> None:
    nutrition = SimpleNamespace(
        kcal=Decimal(100),
        carb_g=Decimal(10),
        protein_g=Decimal(1),
        fat_g=Decimal(1),
        fiber_g=Decimal(1),
        sodium_mg=Decimal(1),
        oil_estimated=False,
        gi_band_label="低",
        gi_band_source="待核对",
        gl_estimate=Decimal(5),
    )
    monkeypatch.setattr("app.services.reports.recipe_nutrition", lambda _session, _recipe: nutrition)
    monkeypatch.setattr(
        "app.services.reports.get_by_user_id",
        lambda _session, _user_id: SimpleNamespace(daily_kcal_target=1650),
    )
    plan = SimpleNamespace(
        id=4,
        servings=Decimal(2),
        meal_type="早餐",
    )
    recipe = SimpleNamespace(id=8, name="燕麦粥")
    session = MagicMock()
    session.execute.return_value.all.return_value = [(plan, recipe)]
    report = daily_report(session, 1, date(2026, 10, 30))
    assert report["totals"]["kcal"] == 200.0
    assert report["items"][0]["servings"] == 2.0
    assert report["items"][0]["gi_band_source"] == "待核对"


def _sample_report() -> dict[str, object]:
    return assemble_daily(date(2026, 10, 30), [_dish()], 1650, "待核对")


def test_cloud_failure_uses_template_without_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def cloud(_settings: object) -> None:
        raise TimeoutError("cloud")

    def local(_settings: object) -> None:
        calls.append("ollama")
        raise AssertionError("报告说明不应调用本机对话模型")

    monkeypatch.setattr("app.services.reports.daily_report", lambda *_args, **_kwargs: _sample_report())
    monkeypatch.setattr(
        "app.services.reports._retrieve",
        lambda _question: ("up", [{"chunk_id": "c1", "page": 7, "text": "主食要定量"}]),
    )
    monkeypatch.setattr("app.core.llm.cloud_client", cloud)
    monkeypatch.setattr("app.core.llm.ollama_client", local)
    result = explain_report(MagicMock(), 1, scope="daily", day=date(2026, 10, 30))
    assert result["rag"] == "up"
    assert result["citation_ids"] == ["c1"]
    assert "依据见检索片段" in str(result["summary"])
    assert "9999" not in str(result["summary"])
    assert calls == []


def test_invented_number_or_range_or_citation_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = iter(
        [
            json.dumps({"summary": "热量是 9999 kcal", "citation_ids": ["c1"]}, ensure_ascii=False),
            json.dumps({"summary": "供能比应在 45%–60%", "citation_ids": ["c1"]}, ensure_ascii=False),
            json.dumps({"summary": "今日热量 100 kcal", "citation_ids": ["nope"]}, ensure_ascii=False),
        ]
    )

    def generate(_messages: object, *, purpose: str) -> str:
        assert purpose == "recommend"
        return next(replies)

    monkeypatch.setattr("app.services.reports.generate", generate)
    monkeypatch.setattr("app.services.reports.daily_report", lambda *_args, **_kwargs: _sample_report())
    monkeypatch.setattr(
        "app.services.reports._retrieve",
        lambda _question: ("up", [{"chunk_id": "c1", "page": 7, "text": "主食"}]),
    )
    for _ in range(3):
        result = explain_report(MagicMock(), 1, scope="daily")
        assert "9999" not in str(result["summary"])
        assert "45%" not in str(result["summary"])
        assert "nope" not in result["citation_ids"]
        assert result["citation_ids"] == ["c1"]
        assert str(result["summary"]).startswith("今日热量 100 kcal")


def test_missing_chunks_omit_guideline_wording(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.reports.daily_report", lambda *_args, **_kwargs: _sample_report())
    monkeypatch.setattr("app.services.reports._retrieve", lambda _question: ("down", []))
    monkeypatch.setattr(
        "app.core.llm.cloud_client",
        lambda _settings: (_ for _ in ()).throw(TimeoutError("cloud")),
    )
    monkeypatch.setattr(
        "app.core.llm.ollama_client",
        lambda _settings: (_ for _ in ()).throw(AssertionError("ollama")),
    )
    result = explain_report(MagicMock(), 1, scope="daily")
    assert result["rag"] == "down"
    assert result["citation_ids"] == []
    assert "依据见检索片段" not in str(result["summary"])
    assert "第" not in str(result["summary"])


@pytest.fixture
def client() -> Iterator[TestClient]:
    def override_session() -> Iterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_report_requires_token(client: TestClient) -> None:
    daily = client.get("/api/v1/report/daily")
    weekly = client.get("/api/v1/report/weekly")
    explained = client.post("/api/v1/report/explain", json={"scope": "daily"})
    assert daily.status_code == 401
    assert weekly.status_code == 401
    assert explained.status_code == 401
    assert daily.json()["code"] == "unauthorized"
