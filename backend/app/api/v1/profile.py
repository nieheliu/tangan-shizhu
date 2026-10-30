from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import record_audit
from app.db.session import get_session
from app.models.entities import User
from app.schemas.profile import (
    ProfilePreview,
    ProfilePreviewInput,
    ProfileUpdate,
    ProfileView,
)
from app.services.profile import get_profile_view, preview_profile, update_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileView)
def read_profile(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ProfileView:
    return get_profile_view(session, user.id)


@router.put("", response_model=ProfileView)
def put_profile(
    body: ProfileUpdate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ProfileView:
    saved = update_profile(session, user.id, body)
    record_audit(
        action="profile.update",
        target=f"user:{user.id}",
        request_id=request.state.request_id,
        actor_id=str(user.id),
    )
    return saved


@router.post("/preview", response_model=ProfilePreview)
def preview(
    body: ProfilePreviewInput,
    _user: Annotated[User, Depends(get_current_user)],
) -> ProfilePreview:
    return preview_profile(body)
