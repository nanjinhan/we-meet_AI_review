"""주간 aspect 집계 (weekly_aspect_stats). 대시보드·리포트·AI비서의 단일 소스.

리뷰 분석이 끝날 때마다 해당 주 row 를 UPSERT — 실시간 재계산 금지(읽기 쿼리 단순화).
집계 로직은 순수 함수 compute_week_stats 로 분리해 수기 검산이 가능하게 했다.

주의 — 경쟁매장 통계 모델: weekly_aspect_stats 의 키가 (store_id, week, aspect)뿐이므로
경쟁매장은 **자체 stores 행**을 가져야 통계가 분리된다(시드 스펙 "매장 2+경쟁 2"와 일치).
경쟁 채널을 내 store_id 밑에 두면 내 통계에 섞이므로 금지 — T-13(비교)에서 강제/검증한다.
(TECH_SPEC §4.2, BACKEND.md §6)
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review, ReviewAnalysis, StoreChannel, WeeklyAspectStats

OVERALL = "전체"


def week_start_of(d: date) -> date:
    """해당 날짜가 속한 주의 월요일."""
    return d - timedelta(days=d.weekday())


@dataclass
class AnalyzedReview:
    rating: int | None
    sentiment: str | None  # pos/neu/neg
    aspects: list[dict]  # [{"category":..., "polarity":"pos"|"neg"}]


@dataclass
class StatRow:
    aspect: str
    pos_cnt: int
    neg_cnt: int
    total_cnt: int
    avg_rating: float | None


def _avg(ratings: list[int]) -> float | None:
    return round(sum(ratings) / len(ratings), 2) if ratings else None


def compute_week_stats(reviews: list[AnalyzedReview]) -> list[StatRow]:
    """한 주의 분석된 리뷰들 → 집계 행 목록('전체' + aspect별).

    - 전체: 리뷰 sentiment 기준. total=리뷰 수, avg_rating=전체 평점 평균.
    - aspect별: 언급된 aspect 항목의 polarity 기준. total=pos+neg,
      avg_rating=해당 aspect 를 언급한 리뷰들의 평점 평균. (언급 없는 aspect 는 행 없음)
    """
    rows: list[StatRow] = [
        StatRow(
            aspect=OVERALL,
            pos_cnt=sum(1 for r in reviews if r.sentiment == "pos"),
            neg_cnt=sum(1 for r in reviews if r.sentiment == "neg"),
            total_cnt=len(reviews),
            avg_rating=_avg([r.rating for r in reviews if r.rating is not None]),
        )
    ]

    # aspect별 집계
    pos: dict[str, int] = {}
    neg: dict[str, int] = {}
    ratings_by_aspect: dict[str, list[int]] = {}
    for r in reviews:
        mentioned = {a["category"] for a in r.aspects}
        for cat in mentioned:
            if r.rating is not None:
                ratings_by_aspect.setdefault(cat, []).append(r.rating)
        for a in r.aspects:
            cat, pol = a["category"], a["polarity"]
            if pol == "pos":
                pos[cat] = pos.get(cat, 0) + 1
            elif pol == "neg":
                neg[cat] = neg.get(cat, 0) + 1

    for cat in sorted(set(pos) | set(neg)):
        p, n = pos.get(cat, 0), neg.get(cat, 0)
        rows.append(
            StatRow(
                aspect=cat,
                pos_cnt=p,
                neg_cnt=n,
                total_cnt=p + n,
                avg_rating=_avg(ratings_by_aspect.get(cat, [])),
            )
        )
    return rows


async def _fetch_week_reviews(
    db: AsyncSession, store_id: int, week_start: date
) -> list[AnalyzedReview]:
    """해당 매장의 해당 주(written_at 기준) 분석 완료 리뷰."""
    week_end = week_start + timedelta(days=7)
    stmt = (
        select(Review.rating, ReviewAnalysis.sentiment, ReviewAnalysis.aspects)
        .join(ReviewAnalysis, ReviewAnalysis.review_id == Review.id)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            StoreChannel.store_id == store_id,
            Review.written_at >= week_start,
            Review.written_at < week_end,
            ReviewAnalysis.model_ver != "failed",  # 실패 배치 제외
        )
    )
    rows = (await db.execute(stmt)).all()
    return [
        AnalyzedReview(rating=rating, sentiment=sentiment, aspects=aspects or [])
        for rating, sentiment, aspects in rows
    ]


async def upsert_week_stats(db: AsyncSession, store_id: int, week_start: date) -> int:
    """해당 주를 재집계해 weekly_aspect_stats 에 UPSERT. 쓴 행 수 반환. (커밋은 호출자)"""
    reviews = await _fetch_week_reviews(db, store_id, week_start)
    rows = compute_week_stats(reviews)
    for row in rows:
        stmt = (
            pg_insert(WeeklyAspectStats)
            .values(
                store_id=store_id,
                week_start=week_start,
                aspect=row.aspect,
                pos_cnt=row.pos_cnt,
                neg_cnt=row.neg_cnt,
                total_cnt=row.total_cnt,
                avg_rating=row.avg_rating,
            )
            .on_conflict_do_update(
                index_elements=["store_id", "week_start", "aspect"],
                set_={
                    "pos_cnt": row.pos_cnt,
                    "neg_cnt": row.neg_cnt,
                    "total_cnt": row.total_cnt,
                    "avg_rating": row.avg_rating,
                },
            )
        )
        await db.execute(stmt)
    return len(rows)
