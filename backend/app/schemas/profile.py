from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.services.nutrition import KCAL_SOURCE


def _clean(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        name = item.strip()
        if not name or name in seen:
            continue
        if len(name) > 32:
            raise ValueError("每一项不能超过 32 个字")
        seen.append(name)
    return seen


class Preferences(BaseModel):
    tastes: list[str] = Field(default_factory=list, max_length=20)
    cuisines: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tastes", "cuisines")
    @classmethod
    def clean_names(cls, value: list[str]) -> list[str]:
        return _clean(value)


class ProfileUpdate(BaseModel):
    gender: str = Field(pattern="^(男|女)$")
    birth_year: int = Field(ge=1900, le=2100)
    height_cm: Decimal = Field(gt=105, le=230)
    weight_kg: Decimal = Field(gt=20, le=300)
    activity_level: str = Field(pattern="^(轻|中|重)$")
    diseases: list[str] = Field(default_factory=list, max_length=20)
    fasting_glucose: Decimal | None = Field(default=None, gt=0, le=40)
    hba1c: Decimal | None = Field(default=None, gt=0, le=30)
    allergies: list[str] = Field(default_factory=list, max_length=40)
    dislikes: list[str] = Field(default_factory=list, max_length=40)
    preferences: Preferences = Field(default_factory=Preferences)
    daily_kcal_target: int | None = Field(default=None, gt=0, le=10000)

    @field_validator("diseases", "allergies", "dislikes")
    @classmethod
    def clean_names(cls, value: list[str]) -> list[str]:
        return _clean(value)


class ProfilePreviewInput(BaseModel):
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    height_cm: Decimal | None = Field(default=None, gt=105, le=230)
    weight_kg: Decimal | None = Field(default=None, gt=20, le=300)
    activity_level: str | None = Field(default=None, pattern="^(轻|中|重)$")


class ProfileView(BaseModel):
    gender: str | None = None
    birth_year: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity_level: str | None = None
    diseases: list[str] = Field(default_factory=list)
    fasting_glucose: float | None = None
    hba1c: float | None = None
    allergies: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    daily_kcal_target: int | None = None
    age: int | None = None
    bmi: float | None = None
    ideal_weight_kg: float | None = None
    suggested_kcal: int | None = None
    kcal_per_kg: int | None = None
    kcal_source: str = KCAL_SOURCE
    recipe_allowed: bool = True
    recipe_block_message: str | None = None


class ProfilePreview(BaseModel):
    age: int | None = None
    bmi: float | None = None
    ideal_weight_kg: float | None = None
    suggested_kcal: int | None = None
    kcal_per_kg: int | None = None
    kcal_source: str = KCAL_SOURCE
    can_save: bool = False
    block_message: str | None = None
