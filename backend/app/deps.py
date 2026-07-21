"""인증·소유권 FastAPI 의존성.

- Supabase JWT 검증은 여기 한 곳에서만 한다(미들웨어 아님). 프로젝트가 비대칭 키(ES256)로
  바뀌면 이 파일의 get_current_user 만 JWKS 검증으로 교체한다.
- 모든 데이터 라우터는 get_owned_store / get_owned_review / get_owned_reply 중 하나를 통과해야 한다.
  존재 은닉을 위해 소유하지 않은 리소스는 401 이 아니라 404 로 응답한다.
(CLAUDE.md 규칙 8, ARCHITECTURE.md §3-3, BACKEND.md §3)
"""

import hmac
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import Reply, Review, Store, StoreChannel


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않은 인증 정보입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _not_found() -> HTTPException:
    # 소유하지 않은 리소스도 '없음'으로 취급해 존재 여부를 숨긴다.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="찾을 수 없습니다.")


async def get_current_user(authorization: str | None = Header(default=None)) -> UUID:
    """Bearer 토큰에서 Supabase JWT(HS256) 검증 후 user id(sub)를 반환. 실패 시 401."""
    if not authorization:
        raise _credentials_error()
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        raise _credentials_error() from None

    sub = payload.get("sub")
    if not sub:
        raise _credentials_error()
    try:
        return UUID(str(sub))
    except (ValueError, TypeError):
        raise _credentials_error() from None


async def get_owned_store(
    store_id: int,
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Store:
    """경로의 store_id 가 현재 사용자 소유인지 검사. 아니면 404."""
    store = await db.get(Store, store_id)
    if store is None or store.owner_id != user:
        raise _not_found()
    return store


async def get_owned_review(
    review_id: int,
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Review:
    """review → channel → store 조인으로 소유 매장의 리뷰인지 검사. 아니면 404."""
    stmt = (
        select(Review)
        .join(StoreChannel, Review.channel_id == StoreChannel.id)
        .join(Store, StoreChannel.store_id == Store.id)
        .where(Review.id == review_id, Store.owner_id == user)
    )
    review = (await db.execute(stmt)).scalar_one_or_none()
    if review is None:
        raise _not_found()
    return review


async def get_owned_reply(
    reply_id: int,
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Reply:
    """reply → review → channel → store 조인으로 소유 매장의 답글인지 검사. 아니면 404."""
    stmt = (
        select(Reply)
        .join(Review, Reply.review_id == Review.id)
        .join(StoreChannel, Review.channel_id == StoreChannel.id)
        .join(Store, StoreChannel.store_id == Store.id)
        .where(Reply.id == reply_id, Store.owner_id == user)
    )
    reply = (await db.execute(stmt)).scalar_one_or_none()
    if reply is None:
        raise _not_found()
    return reply


async def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    """/internal/* 전용. settings.internal_api_key 와 상수시간 비교. 불일치 시 401."""
    # bytes 로 비교: 비ASCII 헤더값이 와도 TypeError(→500) 없이 안전하게 처리한다.
    if x_internal_key is None or not hmac.compare_digest(
        x_internal_key.encode("utf-8"), settings.internal_api_key.encode("utf-8")
    ):
        raise _credentials_error()
