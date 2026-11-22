"""실행 과제 라우터 — 근거를 보고 고른 행동을 기록하고, 이후 리뷰를 관측한다.

- GET    /stores/{id}/actions     목록 + 실행 전/후 관측
- POST   /stores/{id}/actions     기록
- PATCH  /actions/{action_id}     수정(내용·실행일·상태)
- DELETE /actions/{action_id}     삭제

서버는 '효과가 있었다'는 판정을 하지 않는다 — 전/후 건수만 내려준다(services/actions.py).
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_owned_action, get_owned_store
from app.models import ActionItem, Store
from app.schemas.actions import ActionCreate, ActionOut, ActionUpdate
from app.services.actions import action_out, list_actions

router = APIRouter(tags=["actions"])


@router.get("/stores/{store_id}/actions", response_model=list[ActionOut])
async def get_actions(
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> list[ActionOut]:
    return await list_actions(db, store.id)


@router.post(
    "/stores/{store_id}/actions", response_model=ActionOut, status_code=status.HTTP_201_CREATED
)
async def create_action(
    payload: ActionCreate,
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> ActionOut:
    action = ActionItem(
        store_id=store.id,
        aspect=payload.aspect,
        polarity=payload.polarity,
        title=payload.title,
        note=payload.note or None,
        started_on=payload.started_on,
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)  # status·created_at 기본값 로딩
    return await action_out(db, action)


@router.patch("/actions/{action_id}", response_model=ActionOut)
async def update_action(
    payload: ActionUpdate,
    action: ActionItem = Depends(get_owned_action),
    db: AsyncSession = Depends(get_db),
) -> ActionOut:
    changes = payload.model_dump(exclude_unset=True)
    if "note" in changes:
        action.note = changes.pop("note") or None  # null/빈 문자열 → 메모 지움
    for field, value in changes.items():
        if value is not None:  # title/started_on/status 는 null 로 지울 수 없다
            setattr(action, field, value)
    await db.commit()
    await db.refresh(action)
    return await action_out(db, action)


@router.delete("/actions/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action(
    action: ActionItem = Depends(get_owned_action),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await db.delete(action)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
