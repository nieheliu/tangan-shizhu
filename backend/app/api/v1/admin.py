from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_session
from app.models.entities import User
from app.repositories.users import count_users

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def stats(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[User, Depends(require_admin)],
) -> dict[str, int]:
    return {"users": count_users(session)}
