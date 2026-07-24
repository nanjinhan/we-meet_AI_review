"""대시보드 집계 — weekly_aspect_stats 중심 + 답변율/키워드 보조.

프론트는 이 한 번의 호출로 점수·추세·aspect·키워드를 받는다(프론트 집계 금지, FRONTEND.md §4).
today 를 주입 가능하게 해 테스트에서 기간 창을 고정한다.
(BACKEND.md §9, TECH_SPEC §7)
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Reply,
    Review,
    ReviewAnalysis,
    StoreChannel,
    WeeklyAspectStats,
)
from app.pipeline.stats import OVERALL, week_start_of
from app.schemas.dashboard import AspectBar, DashboardOut, RatingBucket, WeeklyPoint
from app.services.score import composite_score


def parse_range_weeks(range_: str) -> int:
    """'4w' → 4. 잘못된 값은 4로, 1~12 로 클램프."""
    try:
        n = int(range_.rstrip("wW"))
    except ValueError:
        n = 4
    return max(1, min(n, 12))


@dataclass
class _RangeMetrics:
    score: float
    total: int
    pos_ratio: float
    avg_rating: float | None
    answer_rate: float


def _recent_weeks(today: date, n: int, *, offset: int = 0) -> list[date]:
    cur = week_start_of(today)
    return [cur - timedelta(weeks=offset + i) for i in range(n)]


async def _overall_rows(db, store_id, weeks):
    stmt = select(WeeklyAspectStats).where(
        WeeklyAspectStats.store_id == store_id,
        WeeklyAspectStats.week_start.in_(weeks),
        WeeklyAspectStats.aspect == OVERALL,
    )
    return list((await db.execute(stmt)).scalars())


async def _answer_rate(db, store_id, weeks) -> tuple[float, int]:
    """(답변율, 기간 내 리뷰 수). 답변=승인된 답글 존재."""
    if not weeks:
        return 0.0, 0
    start, end = min(weeks), max(weeks) + timedelta(weeks=1)
    base = (
        select(Review.id)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            StoreChannel.store_id == store_id,
            StoreChannel.is_competitor.is_(False),
            Review.written_at >= start,
            Review.written_at < end,
        )
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    if total == 0:
        return 0.0, 0
    approved = base.where(
        select(Reply.id)
        .where(Reply.review_id == Review.id, Reply.status == "approved")
        .exists()
    )
    answered = (
        await db.execute(select(func.count()).select_from(approved.subquery()))
    ).scalar_one()
    return round(answered / total, 3), total


async def _range_metrics(db, store_id, weeks) -> _RangeMetrics:
    rows = await _overall_rows(db, store_id, weeks)
    total = sum(r.total_cnt for r in rows)
    pos = sum(r.pos_cnt for r in rows)
    pos_ratio = round(pos / total, 3) if total else 0.0
    rated = [(float(r.avg_rating), r.total_cnt) for r in rows if r.avg_rating and r.total_cnt]
    avg_rating = (
        round(sum(a * c for a, c in rated) / sum(c for _, c in rated), 2) if rated else None
    )
    answer_rate, _ = await _answer_rate(db, store_id, weeks)
    return _RangeMetrics(
        score=composite_score(pos_ratio, avg_rating, answer_rate),
        total=total,
        pos_ratio=pos_ratio,
        avg_rating=avg_rating,
        answer_rate=answer_rate,
    )


async def _trend(db, store_id, weeks) -> list[WeeklyPoint]:
    rows = {r.week_start: r for r in await _overall_rows(db, store_id, weeks)}
    points = []
    for wk in sorted(weeks):  # 오래된→최신
        r = rows.get(wk)
        points.append(
            WeeklyPoint(
                week_start=wk,
                total_cnt=r.total_cnt if r else 0,
                pos_cnt=r.pos_cnt if r else 0,
                neg_cnt=r.neg_cnt if r else 0,
                avg_rating=float(r.avg_rating) if r and r.avg_rating else None,
            )
        )
    return points


async def _aspects(db, store_id, weeks) -> list[AspectBar]:
    stmt = (
        select(
            WeeklyAspectStats.aspect,
            func.sum(WeeklyAspectStats.pos_cnt),
            func.sum(WeeklyAspectStats.neg_cnt),
            func.sum(WeeklyAspectStats.total_cnt),
        )
        .where(
            WeeklyAspectStats.store_id == store_id,
            WeeklyAspectStats.week_start.in_(weeks),
            WeeklyAspectStats.aspect != OVERALL,
        )
        .group_by(WeeklyAspectStats.aspect)
    )
    rows = (await db.execute(stmt)).all()
    bars = [
        AspectBar(aspect=a, pos_cnt=int(p), neg_cnt=int(n), total_cnt=int(t))
        for a, p, n, t in rows
    ]
    bars.sort(key=lambda b: b.total_cnt, reverse=True)
    return bars


async def _keywords(db, store_id, weeks, *, top: int = 8) -> list[str]:
    if not weeks:
        return []
    start, end = min(weeks), max(weeks) + timedelta(weeks=1)
    stmt = (
        select(ReviewAnalysis.keywords)
        .join(Review, Review.id == ReviewAnalysis.review_id)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            StoreChannel.store_id == store_id,
            StoreChannel.is_competitor.is_(False),
            ReviewAnalysis.sentiment == "neg",
            Review.written_at >= start,
            Review.written_at < end,
        )
    )
    counter: Counter = Counter()
    for (keywords,) in (await db.execute(stmt)).all():
        counter.update(keywords or [])
    return [kw for kw, _ in counter.most_common(top)]


async def _rating_dist(db, store_id, weeks) -> list[RatingBucket]:
    """기간 내(경쟁 제외) 평점 분포 5→1. 빈 구간도 count 0 으로 채운다."""
    if not weeks:
        return []
    start, end = min(weeks), max(weeks) + timedelta(weeks=1)
    stmt = (
        select(Review.rating, func.count())
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            StoreChannel.store_id == store_id,
            StoreChannel.is_competitor.is_(False),
            Review.written_at >= start,
            Review.written_at < end,
            Review.rating.is_not(None),
        )
        .group_by(Review.rating)
    )
    counts = {int(r): int(c) for r, c in (await db.execute(stmt)).all()}
    total = sum(counts.values())
    return [
        RatingBucket(
            rating=r,
            count=counts.get(r, 0),
            ratio=round(counts.get(r, 0) / total, 3) if total else 0.0,
        )
        for r in range(5, 0, -1)
    ]


async def build_dashboard(
    db: AsyncSession, store_id: int, range_weeks: int = 4, today: date | None = None
) -> DashboardOut:
    today = today or datetime.now(UTC).date()
    weeks = _recent_weeks(today, range_weeks)
    prev_weeks = _recent_weeks(today, range_weeks, offset=range_weeks)

    cur = await _range_metrics(db, store_id, weeks)
    prev = await _range_metrics(db, store_id, prev_weeks)
    delta = round(cur.score - prev.score, 1) if prev.total > 0 else None

    return DashboardOut(
        range_weeks=range_weeks,
        score=cur.score,
        score_delta=delta,
        total_reviews=cur.total,
        positive_ratio=cur.pos_ratio,
        avg_rating=cur.avg_rating,
        answer_rate=cur.answer_rate,
        trend=await _trend(db, store_id, weeks),
        aspects=await _aspects(db, store_id, weeks),
        keywords=await _keywords(db, store_id, weeks),
        rating_dist=await _rating_dist(db, store_id, weeks),
    )
