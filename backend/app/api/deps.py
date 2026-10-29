from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.entities import User
from app.repositories.users import get_by_id
from app.services.auth import AuthError

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if credentials is None:
        raise AuthError(status_code=401, detail="未登录", code="unauthorized")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AuthError(status_code=401, detail="未登录", code="unauthorized") from exc
    user = get_by_id(session, user_id)
    if user is None:
        raise AuthError(status_code=401, detail="未登录", code="unauthorized")
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise AuthError(status_code=403, detail="需要管理员权限", code="forbidden")
    return user
