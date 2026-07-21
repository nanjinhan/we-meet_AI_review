"""온보딩 연동 라우터 — 카카오 토큰 저장 / 웹푸시 구독 저장.

둘 다 현재 사용자(JWT) 기준으로 저장한다.
(BACKEND.md §9 auth.py)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import PushSubscription
from app.notify import kakao
from app.schemas.auth import (
    KakaoCallbackResult,
    PushSubscribeIn,
    PushSubscribeResult,
)

router = APIRouter(tags=["auth"])


@router.get("/auth/kakao/callback", response_model=KakaoCallbackResult)
async def kakao_callback(
    code: str,
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KakaoCallbackResult:
    """카카오 인가 코드를 토큰으로 교환해 kakao_tokens 에 저장."""
    ok = await kakao.exchange_code(db, user, code)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="카카오 연동 실패"
        )
    await db.commit()
    return KakaoCallbackResult(connected=True)


@router.post("/push/subscribe", response_model=PushSubscribeResult)
async def push_subscribe(
    payload: PushSubscribeIn,
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushSubscribeResult:
    """웹푸시 구독 저장(endpoint 기준 upsert)."""
    ins = (
        pg_insert(PushSubscription)
        .values(
            user_id=user,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        )
        .on_conflict_do_update(
            index_elements=["endpoint"],
            set_={"user_id": user, "p256dh": payload.keys.p256dh, "auth": payload.keys.auth},
        )
    )
    await db.execute(ins)
    await db.commit()
    return PushSubscribeResult(ok=True)
