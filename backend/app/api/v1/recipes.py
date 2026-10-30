"""食谱详情。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.entities import User
from app.schemas.recipes import RecipeDetail
from app.services.recipes import get_recipe_detail

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/{recipe_id}", response_model=RecipeDetail)
def read_recipe(
    recipe_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> RecipeDetail:
    return RecipeDetail.model_validate(get_recipe_detail(session, recipe_id))
