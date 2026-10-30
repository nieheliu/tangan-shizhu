"""购物清单。克数由计划食材减去未过期库存得到。"""

from datetime import date as CalendarDate
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ShoppingGenerate(BaseModel):
    scope: Literal["daily", "weekly"] = "daily"
    day: CalendarDate | None = Field(default=None, validation_alias="date")


class ShoppingItemCreate(BaseModel):
    food_id: int
    amount_g: Decimal = Field(gt=0, le=100000)


class ShoppingItemPatch(BaseModel):
    checked: bool | None = None
    amount_g: Decimal | None = Field(default=None, gt=0, le=100000)

    @model_validator(mode="after")
    def require_a_change(self) -> "ShoppingItemPatch":
        if self.checked is None and self.amount_g is None:
            raise ValueError("没有要修改的内容")
        return self


class ShoppingItemView(BaseModel):
    id: int
    food_id: int
    food_name: str
    category: str
    amount_g: float
    quantity: float
    unit: str
    checked: bool


class ShoppingGroup(BaseModel):
    category: str
    items: list[ShoppingItemView]


class ExcludedFood(BaseModel):
    food_id: int
    food_name: str
    reason: str


class ShoppingListView(BaseModel):
    id: int
    start: CalendarDate
    end: CalendarDate
    groups: list[ShoppingGroup]
    excluded: list[ExcludedFood]


class SkippedItem(BaseModel):
    food_name: str
    detail: str


class InventoryAdded(BaseModel):
    id: int
    food_id: int
    food_name: str
    quantity: float
    unit: str
    grams: float | None


class TransferResult(BaseModel):
    added: list[InventoryAdded]
    skipped: list[SkippedItem]
    shopping: ShoppingListView
