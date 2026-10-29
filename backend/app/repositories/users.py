from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import User


def get_by_username(session: Session, username: str) -> User | None:
    return session.scalars(select(User).where(User.username == username)).one_or_none()


def get_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def add_user(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def count_users(session: Session) -> int:
    total = session.scalar(select(func.count()).select_from(User))
    return int(total or 0)
