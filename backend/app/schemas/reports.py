"""营养报告。供能比目标区间和膳食纤维达标克数在核对页码前留空。"""

from datetime import date as CalendarDate
from typing import Literal

from pydantic import BaseModel, Field


class ReportHint(BaseModel):
    code: str
    message: str
    basis: str


class EnergyRatios(BaseModel):
    carb: float | None
    protein: float | None
    fat: float | None
    factor_source: str
    target_range: None = None


class NutrientTotals(BaseModel):
    kcal: float | None
    carb_g: float | None
    protein_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sodium_mg: float | None
    gl_estimate: float | None


class ReportItem(BaseModel):
    meal_plan_id: int
    recipe_id: int
    name: str
    meal_type: str
    servings: float
    kcal: float | None
    carb_g: float | None
    protein_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sodium_mg: float | None
    oil_estimated: bool
    gi_band_label: str | None
    gi_band_source: str
    gl_estimate: float | None
    gl_is_approximate: bool


class DailyReport(BaseModel):
    date: CalendarDate
    meal_count: int
    kcal_target: int | None
    kcal_target_source: str
    totals: NutrientTotals
    energy_ratios: EnergyRatios
    fiber_target_g: None = None
    fiber_target_source: str
    fiber_met_days: None = None
    gl_is_approximate: bool
    hints: list[ReportHint]
    items: list[ReportItem]


class WeekPoint(BaseModel):
    date: CalendarDate
    kcal: float | None
    carb_energy_ratio: float | None
    fiber_g: float | None


class WeeklyReport(BaseModel):
    start: CalendarDate
    end: CalendarDate
    days: list[WeekPoint]
    kcal_average: float | None
    days_with_kcal: int
    carb_energy_ratio: float | None
    energy_factor_source: str
    target_range: None = None
    fiber_target_g: None = None
    fiber_target_source: str
    fiber_met_days: None = None
    hints: list[ReportHint]


class ExplainRequest(BaseModel):
    scope: Literal["daily", "weekly"]
    date: CalendarDate | None = Field(default=None)


class ExplainResponse(BaseModel):
    summary: str
    citation_ids: list[str]
    rag: str
