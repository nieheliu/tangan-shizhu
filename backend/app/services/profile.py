"""健康档案。推荐只读取 recommendation_profile，其中没有血糖和糖化血红蛋白。"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import HealthProfile
from app.repositories.profiles import get_by_user_id, save_profile
from app.schemas.profile import (
    Preferences,
    ProfilePreview,
    ProfilePreviewInput,
    ProfileUpdate,
    ProfileView,
)
from app.services import nutrition
from app.services.nutrition import KCAL_SOURCE, KcalEstimate

UNDERAGE_MESSAGE = "未满18岁不能保存健康档案，也不提供食谱"
RECIPE_BLOCK_MESSAGE = (
    "档案中有肾病或妊娠相关情况，不生成个体化食谱，请就医或咨询医生、营养师。"
)
_BLOCK_MARKERS = ("肾病", "妊娠", "怀孕", "孕")

RECOMMENDATION_FIELDS = frozenset(
    {
        "diseases",
        "allergies",
        "dislikes",
        "preferences",
        "bmi",
        "daily_kcal_target",
        "recipe_allowed",
    }
)


class ProfileError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def recipe_block_message(diseases: list[str]) -> str | None:
    if any(marker in name for name in diseases for marker in _BLOCK_MARKERS):
        return RECIPE_BLOCK_MESSAGE
    return None


def recommendation_profile(profile: HealthProfile) -> dict[str, object]:
    """推荐和规则只能用这些字段。"""
    bmi = None
    if profile.height_cm is not None and profile.weight_kg is not None:
        bmi = _one_decimal(nutrition.body_mass_index(profile.height_cm, profile.weight_kg))
    return {
        "diseases": list(profile.diseases or []),
        "allergies": list(profile.allergies or []),
        "dislikes": list(profile.dislikes or []),
        "preferences": dict(profile.preferences or {}),
        "bmi": bmi,
        "daily_kcal_target": profile.daily_kcal_target,
        "recipe_allowed": recipe_block_message(list(profile.diseases or [])) is None,
    }


def get_profile_view(session: Session, user_id: int) -> ProfileView:
    return _view(get_by_user_id(session, user_id), nutrition.current_year())


def update_profile(session: Session, user_id: int, body: ProfileUpdate) -> ProfileView:
    year = nutrition.current_year()
    if not nutrition.is_adult(body.birth_year, year):
        raise ProfileError(status_code=422, detail=UNDERAGE_MESSAGE, code="underage")
    estimate = nutrition.suggested_daily_kcal(
        body.height_cm, body.weight_kg, body.activity_level
    )
    if estimate is None:
        raise ProfileError(
            status_code=422, detail="无法估算每日热量", code="cannot_estimate"
        )
    profile = get_by_user_id(session, user_id) or HealthProfile(user_id=user_id)
    profile.gender = body.gender
    profile.birth_year = body.birth_year
    profile.height_cm = body.height_cm
    profile.weight_kg = body.weight_kg
    profile.activity_level = body.activity_level
    profile.diseases = body.diseases
    profile.fasting_glucose = body.fasting_glucose
    profile.hba1c = body.hba1c
    profile.allergies = body.allergies
    profile.dislikes = body.dislikes
    profile.preferences = body.preferences.model_dump()
    profile.daily_kcal_target = (
        body.daily_kcal_target
        if body.daily_kcal_target is not None
        else estimate.suggested_kcal
    )
    profile.updated_at = datetime.now(ZoneInfo(get_settings().app_timezone))
    saved = save_profile(session, profile)
    return _view(saved, year)


def preview_profile(body: ProfilePreviewInput) -> ProfilePreview:
    year = nutrition.current_year()
    age = None
    can_save = False
    message = None
    if body.birth_year is not None:
        age = nutrition.age_in_year(body.birth_year, year)
        if nutrition.is_adult(body.birth_year, year):
            can_save = True
        else:
            message = UNDERAGE_MESSAGE
    estimate = nutrition.suggested_daily_kcal(
        body.height_cm, body.weight_kg, body.activity_level
    )
    bmi = None
    if body.height_cm is not None and body.weight_kg is not None:
        bmi = _one_decimal(nutrition.body_mass_index(body.height_cm, body.weight_kg))
    return _preview(age, bmi, estimate, can_save, message)


def _view(profile: HealthProfile | None, year: int) -> ProfileView:
    if profile is None:
        return ProfileView()
    preferences = profile.preferences or {}
    estimate = nutrition.suggested_daily_kcal(
        profile.height_cm, profile.weight_kg, profile.activity_level
    )
    bmi = None
    if profile.height_cm is not None and profile.weight_kg is not None:
        bmi = _one_decimal(nutrition.body_mass_index(profile.height_cm, profile.weight_kg))
    age = None
    if profile.birth_year is not None:
        age = nutrition.age_in_year(profile.birth_year, year)
    block = recipe_block_message(list(profile.diseases or []))
    return ProfileView(
        gender=profile.gender,
        birth_year=profile.birth_year,
        height_cm=_one_decimal(profile.height_cm),
        weight_kg=_places(profile.weight_kg, "0.01"),
        activity_level=profile.activity_level,
        diseases=list(profile.diseases or []),
        fasting_glucose=_one_decimal(profile.fasting_glucose),
        hba1c=_one_decimal(profile.hba1c),
        allergies=list(profile.allergies or []),
        dislikes=list(profile.dislikes or []),
        preferences=Preferences(
            tastes=list(preferences.get("tastes") or []),
            cuisines=list(preferences.get("cuisines") or []),
        ),
        daily_kcal_target=profile.daily_kcal_target,
        age=age,
        bmi=bmi,
        ideal_weight_kg=_one_decimal(estimate.ideal_weight_kg) if estimate else None,
        suggested_kcal=estimate.suggested_kcal if estimate else None,
        kcal_per_kg=estimate.kcal_per_kg if estimate else None,
        kcal_source=KCAL_SOURCE,
        recipe_allowed=block is None,
        recipe_block_message=block,
    )


def _preview(
    age: int | None,
    bmi: float | None,
    estimate: KcalEstimate | None,
    can_save: bool,
    message: str | None,
) -> ProfilePreview:
    return ProfilePreview(
        age=age,
        bmi=bmi,
        ideal_weight_kg=_one_decimal(estimate.ideal_weight_kg) if estimate else None,
        suggested_kcal=estimate.suggested_kcal if estimate else None,
        kcal_per_kg=estimate.kcal_per_kg if estimate else None,
        kcal_source=KCAL_SOURCE,
        can_save=can_save,
        block_message=message,
    )


def _one_decimal(value: Decimal | None) -> float | None:
    return _places(value, "0.1")


def _places(value: Decimal | None, places: str) -> float | None:
    if value is None:
        return None
    quant = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return float(quant)
