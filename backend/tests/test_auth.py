"""T-03 완료 조건: 잘못된 서명/만료/타 사용자 store 접근이 각각 401/401/404.

가짜 JWT를 secret 으로 직접 서명해 deps 의존성 함수를 직접 호출·검증한다.
(BACKEND.md §3, §11)
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app import deps, models
from app.config import settings


def _make_token(
    sub: str,
    *,
    secret: str | None = None,
    aud: str = "authenticated",
    exp_delta: timedelta = timedelta(hours=1),
) -> str:
    payload = {
        "sub": sub,
        "aud": aud,
        "exp": datetime.now(UTC) + exp_delta,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, secret or settings.supabase_jwt_secret, algorithm="HS256")


# --------------------------- get_current_user ---------------------------
async def test_valid_token_returns_user_id():
    uid = uuid4()
    got = await deps.get_current_user(f"Bearer {_make_token(str(uid))}")
    assert got == uid


async def test_bad_signature_401():
    token = _make_token(str(uuid4()), secret="완전히-다른-시크릿")
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_expired_token_401():
    token = _make_token(str(uuid4()), exp_delta=timedelta(hours=-1))
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_missing_header_401():
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(None)
    assert exc.value.status_code == 401


async def test_wrong_audience_401():
    token = _make_token(str(uuid4()), aud="anon")
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user(f"Bearer {token}")
    assert exc.value.status_code == 401


# --------------------------- get_owned_store ---------------------------
async def test_owned_store_ok_and_cross_user_404(db):
    owner = uuid4()
    other = uuid4()
    store = models.Store(owner_id=owner, name="내매장")
    db.add(store)
    await db.flush()

    # 소유자: 정상 반환
    got = await deps.get_owned_store(store.id, user=owner, db=db)
    assert got.id == store.id

    # 타 사용자: 404
    with pytest.raises(HTTPException) as exc:
        await deps.get_owned_store(store.id, user=other, db=db)
    assert exc.value.status_code == 404

    # 존재하지 않는 store: 404
    with pytest.raises(HTTPException) as exc:
        await deps.get_owned_store(999999999, user=owner, db=db)
    assert exc.value.status_code == 404


# --------------------- get_owned_review / get_owned_reply ---------------------
async def test_owned_review_and_reply_cross_user_404(db):
    owner = uuid4()
    other = uuid4()
    store = models.Store(owner_id=owner, name="조인테스트")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    review = models.Review(channel_id=channel.id, dedup_key="k1", body="본문")
    db.add(review)
    await db.flush()
    reply = models.Reply(review_id=review.id, tone="polite", draft="답글")
    db.add(reply)
    await db.flush()

    # 소유자: 정상
    assert (await deps.get_owned_review(review.id, user=owner, db=db)).id == review.id
    assert (await deps.get_owned_reply(reply.id, user=owner, db=db)).id == reply.id

    # 타 사용자: 404
    with pytest.raises(HTTPException) as exc:
        await deps.get_owned_review(review.id, user=other, db=db)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        await deps.get_owned_reply(reply.id, user=other, db=db)
    assert exc.value.status_code == 404


# --------------------------- require_internal_key ---------------------------
async def test_internal_key_ok_and_reject():
    # 올바른 키: 예외 없음
    await deps.require_internal_key(settings.internal_api_key)

    # 틀린 키 / 누락: 401
    with pytest.raises(HTTPException) as exc:
        await deps.require_internal_key("틀린키")
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        await deps.require_internal_key(None)
    assert exc.value.status_code == 401
