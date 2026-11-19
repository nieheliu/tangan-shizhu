"""问答接口。流式用 fetch 读行，不使用 EventSource。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.entities import User
from app.schemas.chat import (
    ChatMessageView,
    ChatReply,
    ChatRequest,
    ChatSessionDetail,
    ChatSessionSummary,
    ChatSource,
)
from app.services.chat import (
    answer_question,
    list_user_sessions,
    session_detail,
    stream_events,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatReply)
def chat(
    body: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ChatReply:
    result = answer_question(session, user.id, body.message, body.session_id)
    return ChatReply(
        session_id=int(result["session_id"]),
        route=str(result["route"]),  # type: ignore[arg-type]
        blocked=bool(result["blocked"]),
        answer=str(result["answer"]),
        citation_ids=list(result["citation_ids"]),
        sources=[ChatSource.model_validate(item) for item in result["sources"]],
        graph=str(result["graph"]),
        rag=str(result["rag"]),
        pending_profile_id=result.get("pending_profile_id"),  # type: ignore[arg-type]
        draft=dict(result.get("draft") or {}),
    )


@router.post("/stream")
def chat_stream(
    body: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    lines = stream_events(session, user.id, body.message, body.session_id)
    return StreamingResponse(lines, media_type="application/x-ndjson")


@router.get("/sessions", response_model=list[ChatSessionSummary])
def sessions(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[ChatSessionSummary]:
    return [ChatSessionSummary.model_validate(item) for item in list_user_sessions(session, user.id)]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def read_session(
    session_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ChatSessionDetail:
    detail = session_detail(session, user.id, session_id)
    return ChatSessionDetail(
        id=int(detail["id"]),
        messages=[ChatMessageView.model_validate(item) for item in detail["messages"]],
    )
