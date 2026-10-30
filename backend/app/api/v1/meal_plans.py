"""今日计划。同一天同一餐同一道菜重复加入时返回原来的记录。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.entities import User
from app.schemas.meal_plans import MealPlanCreate, MealPlanView
from app.services.meal_plans import add_to_plan

router = APIRouter(prefix="/meal-plans", tags=["meal-plans"])


@router.post("", response_model=MealPlanView)
def create_meal_plan(
    body: MealPlanCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> MealPlanView:
    plan, created = add_to_plan(session, user.id, body.recipe_id, body.meal_type)
    return MealPlanView(
        id=plan.id,
        date=plan.date,
        meal_type=plan.meal_type,
        recipe_id=plan.recipe_id,
        already_added=not created,
    )
