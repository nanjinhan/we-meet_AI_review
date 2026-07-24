"""T-10 완료 조건: httpx/pywebpush mock 테스트 + 토큰 refresh(만료→갱신→재발송).

+ webpush 410 구독삭제, dispatch alerts 로깅, run_digest 중복 방지, auth 엔드포인트.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select

from app import models
from app.config import settings as cfg
from app.notify import dispatch, kakao, webpush
from tests.conftest import auth_headers


# --------------------------- 카카오: 만료 토큰 → refresh → 발송 ---------------------------
async def test_kakao_expired_token_refresh_then_send(db, monkeypatch):
    monkeypatch.setattr(cfg, "kakao_rest_api_key", "testkey")
    calls = {"refresh": 0, "send": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/oauth/token":
            calls["refresh"] += 1
            return httpx.Response(
                200, json={"access_token": "newAT", "expires_in": 21600, "refresh_token": "newRT"}
            )
        if req.url.path.endswith("/memo/default/send"):
            calls["send"] += 1
            assert req.headers["authorization"] == "Bearer newAT"  # 갱신된 토큰으로 발송
            return httpx.Response(200, json={"result_code": 0})
        return httpx.Response(404)

    monkeypatch.setattr(kakao, "_transport", httpx.MockTransport(handler))
    uid = uuid4()
    db.add(
        models.KakaoToken(
            user_id=uid, access_token="oldAT", refresh_token="oldRT",
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # 만료
        )
    )
    await db.flush()

    assert await kakao.send_memo(db, uid, "긴급 리뷰 알림") is True
    assert calls == {"refresh": 1, "send": 1}
    token = await db.get(models.KakaoToken, uid)
    assert token.access_token == "newAT"
    assert token.expires_at > datetime.now(UTC)


async def test_kakao_no_key_skips_without_call(db, monkeypatch):
    monkeypatch.setattr(cfg, "kakao_rest_api_key", "")

    def boom(req):  # 호출되면 실패해야 함
        raise AssertionError("키 없으면 HTTP 호출하면 안 됨")

    monkeypatch.setattr(kakao, "_transport", httpx.MockTransport(boom))
    uid = uuid4()
    db.add(models.KakaoToken(user_id=uid, access_token="a", refresh_token="r",
                             expires_at=datetime.now(UTC) + timedelta(hours=1)))
    await db.flush()
    assert await kakao.send_memo(db, uid, "x") is False


# --------------------------- 웹푸시: 410 → 구독 삭제 ---------------------------
async def test_webpush_410_removes_subscription(db, monkeypatch):
    monkeypatch.setattr(cfg, "vapid_private_key", "vapidkey")
    uid = uuid4()
    db.add(models.PushSubscription(user_id=uid, endpoint="https://good", p256dh="p", auth="a"))
    db.add(models.PushSubscription(user_id=uid, endpoint="https://gone", p256dh="p", auth="a"))
    await db.flush()

    class _Resp:
        status_code = 410

    class Gone(Exception):
        response = _Resp()

    def fake_send(info: dict, data: str) -> None:
        if info["endpoint"] == "https://gone":
            raise Gone()  # 만료된 구독

    monkeypatch.setattr(webpush, "_do_send", fake_send)

    sent = await webpush.send_webpush(db, uid, "제목", "본문")
    assert sent == 1  # good 만 성공
    remaining = (
        await db.execute(
            select(models.PushSubscription).where(models.PushSubscription.user_id == uid)
        )
    ).scalars().all()
    assert [s.endpoint for s in remaining] == ["https://good"]  # gone 삭제됨


# --------------------------- dispatch: 긴급 발송 로깅 + alerted_at ---------------------------
async def _seed_store_review(db, owner, *, urgent, rating, sentiment="neg"):
    store = models.Store(owner_id=owner, name="알림매장")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    review = models.Review(channel_id=channel.id, dedup_key=f"k{uuid4().hex[:8]}",
                           body="이물질이 나왔어요", rating=rating)
    db.add(review)
    await db.flush()
    db.add(models.ReviewAnalysis(review_id=review.id, sentiment=sentiment, severity="complaint",
                                 urgent=urgent, aspects=[], keywords=[], model_ver="m"))
    await db.flush()
    return store, review


async def test_send_urgent_logs_alert_and_marks(db):
    owner = uuid4()
    store, review = await _seed_store_review(db, owner, urgent=True, rating=1)

    alert = await dispatch.send_urgent(db, store.id, review)
    assert alert is not None
    assert alert.kind == "urgent_review"
    assert alert.review_id == review.id
    assert alert.sent_via == []  # 키 미설정 → 발송 채널 없음, 그래도 alerts 로깅
    an = await db.get(models.ReviewAnalysis, review.id)
    assert an.alerted_at is not None  # 중복 방지 마킹


async def test_send_urgent_respects_notify_toggle(db):
    owner = uuid4()
    store, review = await _seed_store_review(db, owner, urgent=True, rating=1)
    db.add(models.StoreSettings(store_id=store.id, notify_urgent=False))
    await db.flush()

    assert await dispatch.send_urgent(db, store.id, review) is None  # 토글 off → 발송 안 함


# --------------------------- run_digest: 그룹핑 + 중복 방지 ---------------------------
async def test_run_digest_groups_and_dedup(db):
    owner = uuid4()
    store = models.Store(owner_id=owner, name="다이제스트매장")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()

    # 일반 부정 3건 (neg, urgent=False, rating=3) → 다이제스트 대상
    for i in range(3):
        r = models.Review(channel_id=channel.id, dedup_key=f"g{i}", body=f"별로{i}", rating=3)
        db.add(r)
        await db.flush()
        db.add(models.ReviewAnalysis(review_id=r.id, sentiment="neg", severity="uncomfortable",
                                     urgent=False, aspects=[], keywords=[], model_ver="m"))
    # 긴급 1건 (urgent) → 다이제스트에서 제외
    ru = models.Review(channel_id=channel.id, dedup_key="urg", body="이물질", rating=1)
    db.add(ru)
    await db.flush()
    db.add(models.ReviewAnalysis(review_id=ru.id, sentiment="neg", severity="complaint",
                                 urgent=True, aspects=[], keywords=[], model_ver="m"))
    await db.flush()

    # run_digest 는 DB 전체를 훑으므로(매장 수 반환) 데모 시드가 들어있으면 총계가 달라진다.
    # → 총계 대신 '이 매장' 기준으로 검증한다.
    n = await dispatch.run_digest(db)
    assert n >= 1
    digests = (
        await db.execute(
            select(models.Alert).where(
                models.Alert.kind == "digest", models.Alert.store_id == store.id
            )
        )
    ).scalars().all()
    assert len(digests) == 1  # 3건이 1개 알림으로 묶임

    # 재실행 → 이 매장은 이미 alerted → 추가 알림 없음 (중복 발송 방지)
    await dispatch.run_digest(db)
    again = (
        await db.execute(
            select(models.Alert).where(
                models.Alert.kind == "digest", models.Alert.store_id == store.id
            )
        )
    ).scalars().all()
    assert len(again) == 1


# --------------------------- 엔드포인트 ---------------------------
async def test_push_subscribe_endpoint(client, db):
    user = uuid4()
    res = await client.post(
        "/api/v1/push/subscribe",
        json={"endpoint": "https://push/abc", "keys": {"p256dh": "p", "auth": "a"}},
        headers=auth_headers(user),
    )
    assert res.status_code == 200
    sub = (
        await db.execute(
            select(models.PushSubscription).where(models.PushSubscription.endpoint == "https://push/abc")
        )
    ).scalar_one()
    assert sub.user_id == user


async def test_kakao_callback_endpoint(client, db, monkeypatch):
    monkeypatch.setattr(cfg, "kakao_rest_api_key", "testkey")

    def handler(req):
        return httpx.Response(
            200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 21600}
        )

    monkeypatch.setattr(kakao, "_transport", httpx.MockTransport(handler))
    user = uuid4()
    res = await client.get("/api/v1/auth/kakao/callback?code=abc123", headers=auth_headers(user))
    assert res.status_code == 200
    assert res.json()["connected"] is True
    token = await db.get(models.KakaoToken, user)
    assert token.access_token == "AT"
