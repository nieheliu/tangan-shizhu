from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Food


def find_food_by_name(session: Session, name: str) -> Food | None:
    return session.scalars(select(Food).where(Food.name == name)).one_or_none()
