from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.entities import Food, HealthProfile, MealPlan, Recipe, User

pytestmark = pytest.mark.integration


def test_postgres_stores_jsonb_and_rejects_duplicate_meal_plan() -> None:
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL 未配置")

    suffix = uuid4().hex[:10]
    session_factory = get_sessionmaker()
    with session_factory() as session:
        try:
            user = User(
                username=f"model-{suffix}", password_hash="not-a-real-hash", role="user"
            )
            session.add(user)
            session.flush()
            session.add(
                HealthProfile(
                    user_id=user.id,
                    diseases=["2型糖尿病"],
                    allergies=["虾"],
                    dislikes=["香菜"],
                    preferences={"cuisine": ["清淡"]},
                )
            )
            food = Food(
                name=f"测试食材-{suffix}",
                alias=["别名"],
                category="测试",
                kcal=Decimal("12.34"),
            )
            recipe = Recipe(name=f"测试食谱-{suffix}", meal_types=["早餐"])
            session.add_all([food, recipe])
            session.flush()
            session.add(
                MealPlan(
                    user_id=user.id,
                    date=date(2026, 10, 29),
                    meal_type="早餐",
                    recipe_id=recipe.id,
                    servings=Decimal(1),
                )
            )
            session.flush()
            session.expire_all()

            profile = session.scalars(
                select(HealthProfile).where(HealthProfile.user_id == user.id)
            ).one()
            loaded_food = session.scalars(
                select(Food).where(Food.name == f"测试食材-{suffix}")
            ).one()
            assert profile.diseases == ["2型糖尿病"]
            assert profile.preferences == {"cuisine": ["清淡"]}
            assert loaded_food.alias == ["别名"]
            assert loaded_food.per_g == Decimal("100.00")
            assert loaded_food.kcal == Decimal("12.34")

            session.add(
                MealPlan(
                    user_id=user.id,
                    date=date(2026, 10, 29),
                    meal_type="早餐",
                    recipe_id=recipe.id,
                    servings=Decimal(1),
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
        finally:
            session.rollback()
