"""AI 비서 쿼리 템플릿 (자유 Text-to-SQL 금지, CLAUDE.md 규칙 6).

RouterDecision 의 파라미터를 바인딩하는 사전 정의 함수만 존재한다.
근거 검색은 BGE-M3 임베딩 + pgvector cosine. 임베딩 미가용 시 최근 리뷰로 폴백(best-effort).
(BACKEND.md §10, TECH_SPEC §5.5)
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review, ReviewAnalysis, ReviewEmbedding, StoreChannel, WeeklyAspectStats
from app.pipeline.stats import OVERALL, week_start_of


def _week_starts(weeks: int) -> list[date]:
    cur = week_start_of(datetime.now(UTC).date())
    return [cur - timedelta(weeks=i) for i in range(max(1, weeks))]


async def top_problem_aspects(db: AsyncSession, store_id: int, weeks: int) -> list[dict]:
    """부정 건수 상위 항목 (aspect별). neg_cnt 내림차순."""
    wk = _week_starts(weeks)
    stmt = (
        select(
            WeeklyAspectStats.aspect,
            func.sum(WeeklyAspectStats.neg_cnt),
            func.sum(WeeklyAspectStats.total_cnt),
        )
        .where(
            WeeklyAspectStats.store_id == store_id,
            WeeklyAspectStats.week_start.in_(wk),
            WeeklyAspectStats.aspect != OVERALL,
        )
        .group_by(WeeklyAspectStats.aspect)
        .order_by(func.sum(WeeklyAspectStats.neg_cnt).desc())
    )
    return [
        {"aspect": a, "neg_cnt": int(n), "total_cnt": int(t)}
        for a, n, t in (await db.execute(stmt)).all()
    ]


async def aspect_trend(db: AsyncSession, store_id: int, aspect: str, weeks: int) -> list[dict]:
    """특정 aspect 의 주별 추이 (오래된→최신)."""
    wk = _week_starts(weeks)
    stmt = (
        select(WeeklyAspectStats)
        .where(
            WeeklyAspectStats.store_id == store_id,
            WeeklyAspectStats.week_start.in_(wk),
            WeeklyAspectStats.aspect == aspect,
        )
        .order_by(WeeklyAspectStats.week_start)
    )
    return [
        {
            "week_start": r.week_start.isoformat(),
            "pos_cnt": r.pos_cnt,
            "neg_cnt": r.neg_cnt,
            "total_cnt": r.total_cnt,
        }
        for r in (await db.execute(stmt)).scalars()
    ]


async def compare_period(db: AsyncSession, store_id: int, aspect: str, weeks: int) -> dict:
    """전기간(직전 N주) 대비 부정비율 증감(%p)."""
    cur_wk = _week_starts(weeks)
    prev_wk = [w - timedelta(weeks=weeks) for w in cur_wk]

    async def agg(wks: list[date]) -> tuple[int, int]:
        n, t = (
            await db.execute(
                select(
                    func.sum(WeeklyAspectStats.neg_cnt),
                    func.sum(WeeklyAspectStats.total_cnt),
                ).where(
                    WeeklyAspectStats.store_id == store_id,
                    WeeklyAspectStats.week_start.in_(wks),
                    WeeklyAspectStats.aspect == aspect,
                )
            )
        ).one()
        return int(n or 0), int(t or 0)

    cn, ct = await agg(cur_wk)
    pn, pt = await agg(prev_wk)
    cur_r = cn / ct if ct else 0.0
    prev_r = pn / pt if pt else 0.0
    return {
        "aspect": aspect,
        "current": {"neg": cn, "total": ct},
        "previous": {"neg": pn, "total": pt},
        "neg_ratio_delta_pp": round((cur_r - prev_r) * 100, 1),
    }


async def search_evidence(
    db: AsyncSession,
    store_id: int,
    query_text: str | None,
    sentiment: str | None,
    weeks: int,
    k: int = 5,
) -> list[Review]:
    """근거 리뷰 검색. BGE-M3 임베딩 + pgvector cosine, 미가용 시 최근 리뷰 폴백."""
    wk = _week_starts(weeks)
    start, end = min(wk), max(wk) + timedelta(weeks=1)
    stmt = (
        select(Review)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            StoreChannel.store_id == store_id,
            StoreChannel.is_competitor.is_(False),
            Review.written_at >= start,
            Review.written_at < end,
        )
    )
    if sentiment:
        stmt = stmt.join(ReviewAnalysis, ReviewAnalysis.review_id == Review.id).where(
            ReviewAnalysis.sentiment == sentiment
        )

    vec = None
    if query_text:
        from app.pipeline import embed

        vecs = embed.embed_texts([query_text])
        vec = vecs[0] if vecs else None

    if vec is not None:
        stmt = (
            stmt.join(ReviewEmbedding, ReviewEmbedding.review_id == Review.id)
            .order_by(ReviewEmbedding.embedding.cosine_distance(vec))
            .limit(k)
        )
    else:
        stmt = stmt.order_by(Review.written_at.desc(), Review.id.desc()).limit(k)

    return list((await db.execute(stmt)).scalars().all())
