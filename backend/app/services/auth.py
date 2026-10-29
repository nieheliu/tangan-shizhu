from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import User
from app.repositories.users import add_user, get_by_username


class AuthError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def register_user(session: Session, username: str, password: str) -> User:
    if get_by_username(session, username) is not None:
        raise AuthError(status_code=409, detail="用户名已存在", code="username_taken")
    user = User(username=username, password_hash=hash_password(password), role="user")
    return add_user(session, user)


def login_user(session: Session, username: str, password: str) -> str:
    user = get_by_username(session, username)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError(
            status_code=401, detail="用户名或密码错误", code="invalid_credentials"
        )
    return create_access_token(str(user.id), role=user.role)
