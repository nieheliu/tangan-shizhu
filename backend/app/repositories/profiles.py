from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import HealthProfile


def get_by_user_id(session: Session, user_id: int) -> HealthProfile | None:
    return session.scalars(
        select(HealthProfile).where(HealthProfile.user_id == user_id)
    ).one_or_none()


def save_profile(session: Session, profile: HealthProfile) -> HealthProfile:
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile
