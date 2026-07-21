"""알림 디스패처 — 채널 선택 + alerts 로깅 일원화.

send_urgent(긴급 즉시), send_digest(1시간 묶음), send_report_ready(주간 리포트) + run_digest(수집).
발송 대상은 매장 소유자(store.owner_id). store_settings 토글(notify_urgent/notify_digest) 존중.
발송 후 review_analysis.alerted_at 을 찍어 중복 발송을 막는다.
(BACKEND.md §7, ARCHITECTURE.md §4, TECH_SPEC §6)
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Alert,
    Review,
    ReviewAnalysis,
    Store,
    StoreChannel,
    StoreSettings,
)
from app.notify import kakao, webpush

logger = logging.getLogger("notify.dispatch")

# rating<=2 는 긴급 즉시 발송, 그 위 부정은 다이제스트 (TECH_SPEC §5.1/§6)
LOW_RATING_THRESHOLD = 2


def _now() -> datetime:
    return datetime.now(UTC)


async def _notify_owner(db, store: Store, title: str, text: str, url: str | None) -> list[str]:
    """소유자에게 가능한 채널로 발송, 성공한 채널명 목록 반환."""
    sent: list[str] = []
    if await kakao.send_memo(db, store.owner_id, text, url):
        sent.append("kakao")
    if await webpush.send_webpush(db, store.owner_id, title, text, url) > 0:
        sent.append("webpush")
    return sent


async def _mark_alerted(db, review_ids: list[int]) -> None:
    if review_ids:
        await db.execute(
            update(ReviewAnalysis)
            .where(ReviewAnalysis.review_id.in_(review_ids))
            .values(alerted_at=_now())
        )


async def send_urgent(db: AsyncSession, store_id: int, review: Review) -> Alert | None:
    """긴급/저평점 리뷰 즉시 발송 + alerts 로깅. (커밋은 호출자)"""
    store = await db.get(Store, store_id)
    if store is None:
        return None
    settings_row = await db.get(StoreSettings, store_id)
    if settings_row is not None and not settings_row.notify_urgent:
        return None

    text = f"🚨 [긴급 리뷰] {store.name}\n{review.body[:80]}"
    sent = await _notify_owner(db, store, f"긴급 리뷰 · {store.name}", text, None)

    alert = Alert(store_id=store_id, review_id=review.id, kind="urgent_review", sent_via=sent)
    db.add(alert)
    await _mark_alerted(db, [review.id])
    await db.flush()
    return alert


async def send_digest(db: AsyncSession, store_id: int, reviews: list[Review]) -> Alert | None:
    """일반 부정 리뷰 묶음 발송 + alerts 로깅. 발송 여부와 무관하게 alerted_at 마킹."""
    if not reviews:
        return None
    store = await db.get(Store, store_id)
    if store is None:
        return None
    review_ids = [r.id for r in reviews]
    settings_row = await db.get(StoreSettings, store_id)
    if settings_row is not None and not settings_row.notify_digest:
        await _mark_alerted(db, review_ids)  # 끔 → 재수집 방지 위해 마킹만
        return None

    text = f"📋 [부정 리뷰 {len(reviews)}건] {store.name}\n확인이 필요한 리뷰가 모였습니다."
    sent = await _notify_owner(db, store, f"부정 리뷰 요약 · {store.name}", text, None)

    alert = Alert(store_id=store_id, review_id=None, kind="digest", sent_via=sent)
    db.add(alert)
    await _mark_alerted(db, review_ids)
    await db.flush()
    return alert


async def send_report_ready(db: AsyncSession, store_id: int) -> Alert | None:
    """주간 리포트 완성 알림 (T-12 에서 호출)."""
    store = await db.get(Store, store_id)
    if store is None:
        return None
    text = f"📊 [주간 리포트] {store.name}\n이번 주 진단 리포트가 준비됐습니다."
    sent = await _notify_owner(db, store, f"주간 리포트 · {store.name}", text, None)
    alert = Alert(store_id=store_id, review_id=None, kind="weekly_report", sent_via=sent)
    db.add(alert)
    await db.flush()
    return alert


async def run_digest(db: AsyncSession) -> int:
    """미발송 일반 부정 리뷰(긴급/저평점 제외)를 매장별로 묶어 다이제스트 발송. 매장 수 반환."""
    stmt = (
        select(Review, StoreChannel.store_id)
        .join(ReviewAnalysis, ReviewAnalysis.review_id == Review.id)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            ReviewAnalysis.sentiment == "neg",
            ReviewAnalysis.urgent.is_(False),
            ReviewAnalysis.alerted_at.is_(None),
            StoreChannel.is_competitor.is_(False),  # 경쟁매장은 알림 없음
            or_(Review.rating.is_(None), Review.rating > LOW_RATING_THRESHOLD),
        )
        .order_by(StoreChannel.store_id)
    )
    rows = (await db.execute(stmt)).all()

    by_store: dict[int, list[Review]] = {}
    for review, store_id in rows:
        by_store.setdefault(store_id, []).append(review)

    for store_id, reviews in by_store.items():
        await send_digest(db, store_id, reviews)
    return len(by_store)
