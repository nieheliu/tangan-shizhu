"""购物清单。生成时扣掉未过期库存，过敏原不会出现在清单里。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.entities import User
from app.schemas.shopping import (
    ShoppingGenerate,
    ShoppingItemCreate,
    ShoppingItemPatch,
    ShoppingItemView,
    ShoppingListView,
    TransferResult,
)
from app.services.shopping import (
    add_manual_item,
    generate_list,
    get_list,
    move_checked_to_inventory,
    update_item,
)

router = APIRouter(prefix="/shopping", tags=["shopping"])


@router.post("/generate", response_model=ShoppingListView)
def create_shopping_list(
    body: ShoppingGenerate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ShoppingListView:
    return ShoppingListView.model_validate(
        generate_list(session, user.id, scope=body.scope, day=body.day)
    )


@router.get("/{list_id}", response_model=ShoppingListView)
def read_shopping_list(
    list_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ShoppingListView:
    return ShoppingListView.model_validate(get_list(session, user.id, list_id))


@router.post("/{list_id}/items", response_model=ShoppingListView)
def create_shopping_item(
    list_id: int,
    body: ShoppingItemCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ShoppingListView:
    return ShoppingListView.model_validate(
        add_manual_item(session, user.id, list_id, body.food_id, body.amount_g)
    )


@router.patch("/items/{item_id}", response_model=ShoppingItemView)
def patch_shopping_item(
    item_id: int,
    body: ShoppingItemPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ShoppingItemView:
    return ShoppingItemView.model_validate(
        update_item(
            session,
            user.id,
            item_id,
            checked=body.checked,
            amount_g=body.amount_g,
        )
    )


@router.post("/{list_id}/to-inventory", response_model=TransferResult)
def stock_shopping_list(
    list_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> TransferResult:
    return TransferResult.model_validate(move_checked_to_inventory(session, user.id, list_id))
