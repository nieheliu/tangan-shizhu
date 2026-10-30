"""把食谱加入今日计划。同一天、同一餐、同一道菜只保留一条。"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import MealPlan, Recipe
from app.services.inventory import today_in_app_tz

MEAL_TYPES = ("早餐", "午餐", "晚餐", "加餐")


class MealPlanError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def add_to_plan(
    session: Session,
    user_id: int,
    recipe_id: int,
    meal_type: str,
    plan_date: date | None = None,
) -> tuple[MealPlan, bool]:
    if meal_type not in MEAL_TYPES:
        raise MealPlanError(status_code=422, detail="餐次不正确", code="invalid_meal_type")
    if session.get(Recipe, recipe_id) is None:
        raise MealPlanError(status_code=404, detail="找不到这道食谱", code="recipe_not_found")
    day = plan_date or today_in_app_tz()
    existing = _find(session, user_id, day, meal_type, recipe_id)
    if existing is not None:
        return existing, False
    plan = MealPlan(
        user_id=user_id,
        date=day,
        meal_type=meal_type,
        recipe_id=recipe_id,
        servings=Decimal(1),
    )
    session.add(plan)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _find(session, user_id, day, meal_type, recipe_id)
        if existing is None:
            raise
        return existing, False
    session.refresh(plan)
    return plan, True


def list_plans(session: Session, user_id: int, day: date) -> list[dict[str, object]]:
    rows = session.execute(
        select(MealPlan, Recipe)
        .join(Recipe, MealPlan.recipe_id == Recipe.id)
        .where(MealPlan.user_id == user_id, MealPlan.date == day)
    ).all()
    ranked = sorted(rows, key=lambda row: (_meal_rank(row[0].meal_type), row[0].id))
    return [
        {
            "id": plan.id,
            "date": plan.date,
            "meal_type": plan.meal_type,
            "recipe_id": plan.recipe_id,
            "recipe_name": recipe.name,
            "servings": float(plan.servings),
        }
        for plan, recipe in ranked
    ]


def delete_plan(session: Session, user_id: int, plan_id: int) -> None:
    plan = session.get(MealPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise MealPlanError(status_code=404, detail="找不到这条计划", code="plan_not_found")
    session.delete(plan)
    session.commit()


def _meal_rank(meal_type: str) -> int:
    try:
        return MEAL_TYPES.index(meal_type)
    except ValueError:
        return len(MEAL_TYPES)


def _find(
    session: Session,
    user_id: int,
    day: date,
    meal_type: str,
    recipe_id: int,
) -> MealPlan | None:
    return session.scalar(
        select(MealPlan).where(
            MealPlan.user_id == user_id,
            MealPlan.date == day,
            MealPlan.meal_type == meal_type,
            MealPlan.recipe_id == recipe_id,
        )
    )
