"""加入今日计划。日期由服务器按 Asia/Shanghai 填写。"""

from datetime import date

from pydantic import BaseModel, Field


class MealPlanCreate(BaseModel):
    recipe_id: int
    meal_type: str = Field(max_length=16)


class MealPlanView(BaseModel):
    id: int
    date: date
    meal_type: str
    recipe_id: int
    already_added: bool
