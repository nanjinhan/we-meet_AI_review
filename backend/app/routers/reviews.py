"""리뷰 라우터 — T-04 범위는 CSV 임포트만. 인박스 GET 은 T-11 에서 추가.

(BACKEND.md §9 reviews.py)
"""

import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.csv_import import parse_csv
from app.db import SessionLocal, get_db
from app.deps import get_owned_store
from app.models import Reply, Review, ReviewAnalysis, Store, StoreChannel
from app.schemas.reviews import ReviewItem, ReviewsPage
from app.schemas.stores import ImportResult
from app.services.ingest import store_raw_reviews

logger = logging.getLogger("routers.reviews")
router = APIRouter(tags=["reviews"])


async def _current_replies(db: AsyncSession, review_ids: list[int]) -> dict[int, Reply]:
    """리뷰별 '현재' 답글(폐기 제외 중 최신 id) 매핑."""
    if not review_ids:
        return {}
    stmt = (
        select(Reply)
        .where(Reply.review_id.in_(review_ids), Reply.status != "discarded")
        .order_by(Reply.review_id, Reply.id.desc())
    )
    current: dict[int, Reply] = {}
    for rep in (await db.execute(stmt)).scalars():
        current.setdefault(rep.review_id, rep)  # id desc → 첫 항목이 최신
    return current


@router.get("/stores/{store_id}/reviews", response_model=ReviewsPage)
async def list_reviews(
    store: Store = Depends(get_owned_store),
    sentiment: Literal["pos", "neu", "neg"] | None = None,
    urgent: bool | None = None,
    answered: bool | None = None,
    cursor: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ReviewsPage:
    """리뷰 인박스. 필터(sentiment/urgent/answered) + 커서 페이지네이션(id desc)."""
    approved_exists = (
        select(Reply.id)
        .where(Reply.review_id == Review.id, Reply.status == "approved")
        .exists()
    )
    q = (
        select(Review, ReviewAnalysis)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .outerjoin(ReviewAnalysis, ReviewAnalysis.review_id == Review.id)
        .where(StoreChannel.store_id == store.id)
    )
    if sentiment is not None:
        q = q.where(ReviewAnalysis.sentiment == sentiment)
    if urgent is not None:
        q = q.where(ReviewAnalysis.urgent.is_(urgent))
    if answered is not None:
        q = q.where(approved_exists if answered else ~approved_exists)
    if cursor is not None:
        q = q.where(Review.id < cursor)  # id desc 커서
    q = q.order_by(Review.id.desc()).limit(limit + 1)

    rows = (await db.execute(q)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    replies = await _current_replies(db, [rev.id for rev, _ in rows])
    items = [
        ReviewItem(
            id=rev.id,
            author_masked=rev.author_masked,
            rating=rev.rating,
            body=rev.body,
            written_at=rev.written_at,
            sentiment=an.sentiment if an else None,
            severity=an.severity if an else None,
            urgent=an.urgent if an else False,
            aspects=an.aspects if an else [],
            keywords=list(an.keywords) if an and an.keywords else [],
            answered=(rev.id in replies and replies[rev.id].status == "approved"),
            reply_draft=replies[rev.id].draft if rev.id in replies else None,
        )
        for rev, an in rows
    ]
    next_cursor = rows[-1][0].id if has_more else None
    return ReviewsPage(items=items, next_cursor=next_cursor)


async def _analyze_channel_bg(channel_id: int) -> None:
    """업로드 응답 후 백그라운드로 분석. 요청 세션은 닫혔으므로 새 세션을 연다."""
    from app.pipeline.analyze import analyze_new_reviews

    try:
        async with SessionLocal() as db:
            await analyze_new_reviews(db, channel_id)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - 백그라운드 실패는 요청에 영향 없음
        logger.warning("CSV 임포트 후 분석 실패(channel=%s): %s", channel_id, exc)


@router.post("/stores/{store_id}/reviews:import", response_model=ImportResult)
async def import_reviews(
    background_tasks: BackgroundTasks,
    store: Store = Depends(get_owned_store),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    raws, skipped = parse_csv(await file.read())

    # CSV 채널 find-or-create (매장당 1개)
    stmt = select(StoreChannel).where(
        StoreChannel.store_id == store.id, StoreChannel.platform == "csv"
    )
    channel = (await db.execute(stmt)).scalars().first()
    if channel is None:
        channel = StoreChannel(store_id=store.id, platform="csv")
        db.add(channel)
        await db.flush()

    # on conflict do nothing 으로 중복(dedup_key) 자동 스킵 — 재업로드 시 0행 추가
    imported = await store_raw_reviews(db, channel.id, raws)
    await db.commit()

    # 업로드 후 분석 파이프라인을 백그라운드로 실행 (BACKEND.md §9)
    background_tasks.add_task(_analyze_channel_bg, channel.id)
    return ImportResult(imported=imported, skipped=skipped)
