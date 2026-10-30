from decimal import Decimal

from app.services.nutrition import (
    KCAL_SOURCE,
    age_in_year,
    body_mass_index,
    is_adult,
    kcal_per_kg,
    suggested_daily_kcal,
)


def test_bmi_uses_weight_over_height_squared() -> None:
    bmi = body_mass_index(Decimal(160), Decimal(55))
    assert round(bmi, 1) == Decimal("21.5")


def test_adult_energy_uses_ideal_weight_and_marked_source() -> None:
    estimate = suggested_daily_kcal(Decimal(160), Decimal(55), "中")
    assert estimate is not None
    assert estimate.ideal_weight_kg == Decimal(55)
    assert estimate.kcal_per_kg == 30
    assert estimate.suggested_kcal == 1650
    assert estimate.source == KCAL_SOURCE


def test_kcal_factor_follows_activity_and_bmi_band() -> None:
    assert kcal_per_kg("轻", Decimal(24)) == 20
    assert kcal_per_kg("中", Decimal("18.5")) == 30
    assert kcal_per_kg("中", Decimal("18.4")) == 35
    assert kcal_per_kg("重", Decimal(16)) == 35
    overweight = suggested_daily_kcal(Decimal(170), Decimal(80), "轻")
    assert overweight is not None
    assert overweight.suggested_kcal == 1300


def test_half_kcal_rounds_half_up() -> None:
    estimate = suggested_daily_kcal(Decimal("160.02"), Decimal(55), "轻")
    assert estimate is not None
    assert estimate.suggested_kcal == 1376


def test_age_uses_calendar_year_and_requires_18() -> None:
    assert age_in_year(2008, 2026) == 18
    assert is_adult(2008, 2026)
    assert not is_adult(2009, 2026)


def test_calorie_formula_ignores_glucose() -> None:
    names = suggested_daily_kcal.__code__.co_varnames
    assert "fasting_glucose" not in names
    assert "hba1c" not in names
