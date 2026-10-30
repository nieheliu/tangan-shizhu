from decimal import Decimal

import pytest

from app.rules.engine import (
    GI_HIGH_MIN,
    Rule,
    RuleOutcome,
    RulesError,
    evaluate,
    load_rules,
    recipe_names,
)


def _context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kcal": 400,
        "carb_g": 45,
        "protein_g": 12,
        "fat_g": 8,
        "fiber_g": 2,
        "sodium_mg": 180,
        "main_staple_gi": 55,
        "main_staple_name": "燕麦",
        "food_ids": [1, 2],
        "food_names": ["燕麦", "鸡蛋"],
        "allergen_hit": False,
        "dislike_count": 0,
        "diseases": ["2型糖尿病"],
    }
    base.update(overrides)
    return base


def _ids(outcome: RuleOutcome) -> set[str]:
    return {hit.rule_id for hit in outcome.hits}


def test_common_allergen_rejects_the_recipe() -> None:
    outcome = evaluate(_context(allergen_hit=True, fiber_g=5, main_staple_gi=50))
    assert outcome.rejected
    assert not outcome.blocked
    hit = next(hit for hit in outcome.hits if hit.rule_id == "COMMON-001")
    assert hit.type == "reject"
    assert hit.source
    assert any(item.rule_id == "DM-003" for item in outcome.hits)
    assert outcome.delta == 0


def test_common_dislike_only_lowers_the_score() -> None:
    outcome = evaluate(_context(dislike_count=2, fiber_g=1, main_staple_gi=50))
    assert not outcome.rejected
    hit = next(hit for hit in outcome.hits if hit.rule_id == "COMMON-002")
    assert hit.type == "score"
    assert hit.delta == -2
    assert outcome.delta == -2


def test_diabetes_high_gi_rejects_with_rule_and_source() -> None:
    outcome = evaluate(_context(main_staple_gi=GI_HIGH_MIN))
    assert outcome.rejected
    hit = next(hit for hit in outcome.hits if hit.rule_id == "DM-001")
    assert hit.type == "reject"
    assert "待核对" in hit.source
    assert hit.message
    rule = next(rule for rule in load_rules() if rule.rule_id == "DM-001")
    assert rule.when == f"main_staple_gi >= {GI_HIGH_MIN}"
    below = evaluate(_context(main_staple_gi=Decimal("69.9")))
    assert "DM-001" not in _ids(below)


def test_diabetes_high_gi_does_not_apply_without_the_disease() -> None:
    outcome = evaluate(_context(main_staple_gi=80, diseases=[]))
    assert "DM-001" not in _ids(outcome)
    assert not outcome.rejected


def test_diabetes_null_gi_is_not_high() -> None:
    outcome = evaluate(_context(main_staple_gi=None))
    assert "DM-001" not in _ids(outcome)
    assert not outcome.rejected


def test_diabetes_added_sugar_rule_does_not_fire_without_a_column() -> None:
    outcome = evaluate(_context(fiber_g=1))
    assert "DM-002" not in _ids(outcome)
    loaded = next(rule for rule in load_rules() if rule.rule_id == "DM-002")
    assert "added_sugar_g" in loaded.when
    assert loaded.source == "待核对"


def test_diabetes_fiber_adds_score_without_rejecting() -> None:
    outcome = evaluate(_context(fiber_g=5, main_staple_gi=50))
    assert not outcome.rejected
    hit = next(hit for hit in outcome.hits if hit.rule_id == "DM-003")
    assert hit.delta == 2
    assert hit.source == "待核对"
    assert outcome.delta == 2


def test_diabetes_null_fiber_does_not_score() -> None:
    outcome = evaluate(_context(fiber_g=None, main_staple_gi=50))
    assert "DM-003" not in _ids(outcome)


def test_safety_kidney_blocks_with_medical_advice() -> None:
    outcome = evaluate(_context(diseases=["慢性肾病"], main_staple_gi=80))
    assert outcome.blocked
    assert outcome.rejected
    hit = next(hit for hit in outcome.hits if hit.rule_id == "SAFE-001")
    assert "请就医" in hit.message
    assert outcome.block_message == hit.message
    assert outcome.delta == 0
    assert "DM-001" not in _ids(outcome)


def test_safety_pregnancy_blocks() -> None:
    outcome = evaluate(_context(diseases=["妊娠"]))
    hit = next(hit for hit in outcome.hits if hit.rule_id == "SAFE-002")
    assert outcome.blocked
    assert "请就医" in hit.message


def test_safety_minor_blocks_and_adult_does_not() -> None:
    blocked = evaluate(_context(diseases=[]), age=17)
    assert any(hit.rule_id == "SAFE-003" for hit in blocked.hits)
    assert blocked.block_message is not None
    assert "请就医" in blocked.block_message
    adult = evaluate(_context(diseases=[], main_staple_gi=50), age=18)
    assert "SAFE-003" not in _ids(adult)
    assert not adult.blocked
    unknown_age = evaluate(_context(diseases=[], main_staple_gi=50))
    assert "SAFE-003" not in _ids(unknown_age)


def test_safety_urgent_text_blocks() -> None:
    outcome = evaluate(_context(diseases=[]), user_text="这个药的用药剂量是多少")
    hit = next(hit for hit in outcome.hits if hit.rule_id == "SAFE-004")
    assert outcome.blocked
    assert "请就医" in hit.message


def test_glucose_never_enters_the_rule_names() -> None:
    names = recipe_names(
        {
            "fasting_glucose": 15,
            "hba1c": 9,
            "main_staple_gi": 80,
            "diseases": ["2型糖尿病"],
        }
    )
    assert "fasting_glucose" not in names
    assert "hba1c" not in names
    outcome = evaluate(_context(fasting_glucose=15, hba1c=9, main_staple_gi=80))
    assert any(hit.rule_id == "DM-001" for hit in outcome.hits)


def test_broken_expression_is_an_engine_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.rules.engine.load_rules",
        lambda: (
            Rule(
                rule_id="BAD-001",
                type="reject",
                when="__import__('os')",
                message="无效",
                source="测试",
                delta=0,
                per=None,
                disease=None,
                filename="common.yaml",
            ),
        ),
    )
    with pytest.raises(RulesError, match="规则表达式无法计算"):
        evaluate(_context())
