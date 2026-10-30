"""日报告和周报告。说明文字失败时仍返回已经算好的数字。"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.entities import User
from app.schemas.reports import (
    DailyReport,
    ExplainRequest,
    ExplainResponse,
    WeeklyReport,
)
from app.services.reports import daily_report, explain_report, weekly_report

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/daily", response_model=DailyReport)
def read_daily(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date | None, Query(alias="date")] = None,
) -> DailyReport:
    return DailyReport.model_validate(daily_report(session, user.id, day))


@router.get("/weekly", response_model=WeeklyReport)
def read_weekly(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    end: Annotated[date | None, Query()] = None,
) -> WeeklyReport:
    return WeeklyReport.model_validate(weekly_report(session, user.id, end))


@router.post("/explain", response_model=ExplainResponse)
def explain(
    body: ExplainRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ExplainResponse:
    return ExplainResponse.model_validate(
        explain_report(session, user.id, scope=body.scope, day=body.date)
    )
