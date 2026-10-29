from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import record_audit
from app.db.session import get_session
from app.models.entities import User
from app.schemas.auth import Credentials, TokenResponse, UserPublic
from app.services.auth import login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic)
def register(
    body: Credentials,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> UserPublic:
    user = register_user(session, body.username, body.password)
    record_audit(
        action="auth.register",
        target=f"user:{user.id}",
        request_id=request.state.request_id,
        actor_id=str(user.id),
    )
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(
    body: Credentials,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> TokenResponse:
    token = login_user(session, body.username, body.password)
    record_audit(
        action="auth.login",
        target=body.username,
        request_id=request.state.request_id,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserPublic)
def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
