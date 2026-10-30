from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import record_audit
from app.db.session import get_session
from app.models.entities import User
from app.schemas.inventory import FoodOption, InventoryItemView, InventoryWrite
from app.services.inventory import (
    create_item,
    list_inventory,
    list_reminders,
    remove_item,
    search_food_options,
    update_item,
)

router = APIRouter(tags=["inventory"])


@router.get("/foods/search", response_model=list[FoodOption])
def search_foods(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(max_length=64)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[FoodOption]:
    return search_food_options(session, q, limit)


@router.get("/inventory", response_model=list[InventoryItemView])
def read_inventory(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[InventoryItemView]:
    return list_inventory(session, user.id)


@router.get("/inventory/reminders", response_model=list[InventoryItemView])
def read_reminders(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[InventoryItemView]:
    return list_reminders(session, user.id)


@router.post("/inventory", response_model=InventoryItemView)
def post_inventory(
    body: InventoryWrite,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> InventoryItemView:
    saved = create_item(session, user.id, body)
    record_audit(
        action="inventory.create",
        target=f"inventory:{saved.id}",
        request_id=request.state.request_id,
        actor_id=str(user.id),
    )
    return saved


@router.put("/inventory/{item_id}", response_model=InventoryItemView)
def put_inventory(
    item_id: int,
    body: InventoryWrite,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> InventoryItemView:
    saved = update_item(session, user.id, item_id, body)
    record_audit(
        action="inventory.update",
        target=f"inventory:{saved.id}",
        request_id=request.state.request_id,
        actor_id=str(user.id),
    )
    return saved


@router.delete("/inventory/{item_id}")
def delete_inventory(
    item_id: int,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, bool]:
    remove_item(session, user.id, item_id)
    record_audit(
        action="inventory.delete",
        target=f"inventory:{item_id}",
        request_id=request.state.request_id,
        actor_id=str(user.id),
    )
    return {"ok": True}
