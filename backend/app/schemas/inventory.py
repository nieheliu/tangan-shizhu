from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class FoodOption(BaseModel):
    id: int
    name: str
    category: str | None = None
    units: list[str] = Field(default_factory=list)


class InventoryWrite(BaseModel):
    food_id: int
    quantity: Decimal = Field(gt=0, le=100000)
    unit: str = Field(min_length=1, max_length=32)
    purchased_at: date | None = None
    expires_at: date | None = None

    @field_validator("unit")
    @classmethod
    def strip_unit(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("请填写单位")
        return name

    @model_validator(mode="after")
    def expiry_after_purchase(self) -> "InventoryWrite":
        if (
            self.purchased_at is not None
            and self.expires_at is not None
            and self.expires_at < self.purchased_at
        ):
            raise ValueError("到期日不能早于购买日")
        return self


class InventoryItemView(BaseModel):
    id: int
    food_id: int
    food_name: str
    quantity: float
    unit: str
    grams: float | None
    purchased_at: date | None
    expires_at: date | None
    status: str
