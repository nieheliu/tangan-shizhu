"""问答服务。会话写入 PostgreSQL，营养数字仍来自已有服务。"""

from collections.abc import Iterator
import json
from neo4j.exceptions import Neo4jError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.chat import ChatDeps, FoodRecord, run_chat
from app.graph.queries import GraphQueryError, neighborhood
from app.graph.sync import GraphUnavailable, neo4j_driver
from app.models.entities import Food, HealthProfile
from app.rag.embeddings import embed_texts
from app.rag.retrieve import search_guidelines
from app.rag.vectorstore import chroma_directory, get_collection, open_client
from app.repositories.chats import (
    add_message,
    add_pending,
    add_session,
    get_session_for_user,
    list_messages,
    list_sessions,
)
from app.repositories.profiles import get_by_user_id
from app.services.nutrition import age_in_year, current_year
from app.services.recommend import RecommendDataError, recommend_for_user
from app.services.reports import daily_report, explain_report, weekly_report


class ChatError(Exception):
    def __init__(self, *, status_code: int, detail: str, code: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code


def answer_question(
    session: Session,
    user_id: int,
    message: str,
    session_id: int | None = None,
) -> dict[str, object]:
    cleaned = message.strip()
    if not cleaned:
        raise ChatError(status_code=422, detail="请输入问题", code="message_required")
    chat = _session(session, user_id, session_id)
    add_message(session, chat.id, "user", cleaned)
    result = run_chat(default_deps(session), user_id=user_id, question=cleaned)
    pending_id = None
    draft = result.get("draft") if isinstance(result.get("draft"), dict) else {}
    if result.get("route") == "profile_update":
        pending = add_pending(session, user_id, chat.id, dict(draft or {}))
        pending_id = pending.id
    answer = str(result.get("answer") or "")
    sources = _source_views(result.get("sources"))
    meta = {
        "route": result.get("route"),
        "blocked": result.get("blocked"),
        "citation_ids": result.get("citation_ids") or [],
        "sources": sources,
        "pending_profile_id": pending_id,
        "draft": draft,
    }
    add_message(session, chat.id, "assistant", answer, meta)
    session.commit()
    return {
        "session_id": chat.id,
        "route": result.get("route"),
        "blocked": bool(result.get("blocked")),
        "answer": answer,
        "citation_ids": result.get("citation_ids") or [],
        "sources": sources,
        "graph": result.get("graph") or "up",
        "rag": result.get("rag") or "up",
        "pending_profile_id": pending_id,
        "draft": draft,
    }


def stream_events(
    session: Session,
    user_id: int,
    message: str,
    session_id: int | None = None,
) -> Iterator[str]:
    payload = answer_question(session, user_id, message, session_id)
    answer = str(payload["answer"])
    for index in range(0, len(answer), 12):
        yield _event("token", {"text": answer[index : index + 12]})
    if payload.get("sources"):
        yield _event("sources", {"items": payload["sources"]})
    if payload.get("pending_profile_id") is not None:
        yield _event(
            "profile_pending",
            {
                "pending_profile_id": payload["pending_profile_id"],
                "draft": payload.get("draft") or {},
            },
        )
    yield _event("done", {"session_id": payload["session_id"], "route": payload["route"]})


def list_user_sessions(session: Session, user_id: int) -> list[dict[str, object]]:
    rows = []
    for item in list_sessions(session, user_id):
        messages = list_messages(session, item.id)
        preview = next((row.content for row in messages if row.role == "user"), "新会话")
        rows.append({"id": item.id, "preview": preview[:40]})
    return rows


def session_detail(session: Session, user_id: int, session_id: int) -> dict[str, object]:
    chat = get_session_for_user(session, session_id, user_id)
    if chat is None:
        raise ChatError(status_code=404, detail="找不到这次对话", code="session_not_found")
    return {
        "id": chat.id,
        "messages": [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "meta": row.meta or {},
            }
            for row in list_messages(session, chat.id)
        ],
    }


def default_deps(session: Session) -> ChatDeps:
    foods = list(session.scalars(select(Food)))
    return ChatDeps(
        load_profile=lambda user_id: _profile(session, user_id),
        list_foods=lambda: [
            FoodRecord(
                food_id=food.id,
                name=food.name,
                aliases=tuple(str(item) for item in food.alias or []),
                gi=food.gi,
                gi_source=food.gi_source or "待核对",
                kcal=food.kcal,
                carb_g=food.carb_g,
            )
            for food in foods
        ],
        graph_links=_graph_links,
        retrieve=_retrieve,
        recommend=lambda user_id, meal, only_inventory: recommend_for_user(
            session,
            user_id,
            meal_type=meal,
            only_inventory=only_inventory,
            exclude_ids=[],
        ),
        load_report=lambda user_id, scope: _report(session, user_id, scope),
        explain_report=lambda user_id, scope: explain_report(session, user_id, scope=scope),
    )


def _session(session: Session, user_id: int, session_id: int | None) -> object:
    if session_id is None:
        return add_session(session, user_id)
    row = get_session_for_user(session, session_id, user_id)
    if row is None:
        raise ChatError(status_code=404, detail="找不到这次对话", code="session_not_found")
    return row


def _profile(session: Session, user_id: int) -> dict[str, object]:
    profile = get_by_user_id(session, user_id)
    if profile is None:
        return {"diseases": [], "age": None}
    return {
        "diseases": list(profile.diseases or []),
        "age": _age(profile),
    }


def _age(profile: HealthProfile) -> int | None:
    if profile.birth_year is None:
        return None
    return age_in_year(profile.birth_year, current_year())


def _graph_links(name: str) -> tuple[str, list[dict[str, object]]]:
    try:
        driver = neo4j_driver()
    except GraphUnavailable:
        return "down", []
    try:
        driver.verify_connectivity()
        _center, _nodes, edges = neighborhood(driver, name, 1)
    except (OSError, GraphUnavailable, Neo4jError, GraphQueryError):
        return "down", []
    finally:
        driver.close()
    return "up", [
        {
            "name": item.source.split(":", 1)[-1],
            "relation": item.relation,
            "other": item.target.split(":", 1)[-1],
            "reason": item.reason,
            "citation": item.citation,
        }
        for item in edges
    ]


def _retrieve(question: str) -> tuple[str, list[dict[str, object]]]:
    try:
        collection = get_collection(open_client(str(chroma_directory())))
        hits = search_guidelines(question, collection, embed_texts, limit=4)
    except Exception:  # noqa: BLE001
        return "down", []
    return "up", [
        {
            "chunk_id": hit.chunk_id,
            "source": hit.source,
            "page": hit.page,
            "text": hit.text,
        }
        for hit in hits
    ]


def _report(session: Session, user_id: int, scope: str) -> dict[str, object]:
    if scope == "weekly":
        return weekly_report(session, user_id)
    return daily_report(session, user_id)


def _source_views(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    views: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("chunk_id"):
            continue
        views.append(
            {
                "chunk_id": str(item.get("chunk_id")),
                "source": str(item.get("source") or ""),
                "page": int(item.get("page") or 0),
            }
        )
    return views


def _event(name: str, data: dict[str, object]) -> str:
    return json.dumps({"event": name, **data}, ensure_ascii=False) + "\n"
