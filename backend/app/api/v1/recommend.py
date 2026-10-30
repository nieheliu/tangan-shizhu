"""推荐接口。营养数字来自后端，模型只提供理由和引用。"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.entities import User
from app.schemas.recommend import RecommendRequest, RecommendResponse
from app.services.recommend import recommend_for_user, save_recommend_log

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend(
    body: RecommendRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> RecommendResponse:
    started = time.perf_counter()
    result = recommend_for_user(
        session,
        user.id,
        meal_type=body.meal_type,
        only_inventory=body.only_inventory,
        exclude_ids=body.exclude_ids,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    save_recommend_log(
        session,
        user_id=user.id,
        request=body.model_dump(),
        result=result,
        rejected=list(result.get("rejected") or []),
        latency_ms=elapsed,
    )
    return RecommendResponse.model_validate(result)
