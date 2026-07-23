"""경쟁매장 비교 — 우리 vs 경쟁 aspect 통계 + 한 줄 인사이트.

경쟁매장은 자체 stores 행을 가지며 store_channels.competitor_of 로 우리 매장에 연결된다
(통계 분리를 위해 — weekly_aspect_stats PK 가 (store_id, week, aspect)). 경쟁 채널은
분석·집계까지만 수행되고 답글·알림은 생성되지 않는다(analyze.py/reply_gen.py 에서 차단).

인사이트는 결정론적 규칙 기반(무료·환각 없음). 추후 리포트 생성 시 캐시된 LLM 인사이트로 교체 가능.
(BACKEND.md §9, TECH_SPEC §5.4)
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StoreChannel, WeeklyAspectStats
from app.pipeline.stats import OVERALL
from app.schemas.compare import CompareAspect, CompareOut
from app.services.dashboard import _recent_weeks

# 부정비율 격차가 이 이상이면 "개선 필요"로 강조 (10%p)
INSIGHT_MARGIN = 0.1


async def _competitor_store_ids(db, store_id) -> list[int]:
    return list(
        (
            await db.execute(
                select(StoreChannel.store_id)
                .where(StoreChannel.competitor_of == store_id)
                .distinct()
            )
        ).scalars()
    )


async def _aspect_agg(db, store_ids, weeks) -> dict[str, tuple[int, int, int]]:
    """store_ids 의 aspect별 (pos, neg, total) 합계 ('전체' 제외)."""
    if not store_ids:
        return {}
    stmt = (
        select(
            WeeklyAspectStats.aspect,
            func.sum(WeeklyAspectStats.pos_cnt),
            func.sum(WeeklyAspectStats.neg_cnt),
            func.sum(WeeklyAspectStats.total_cnt),
        )
        .where(
            WeeklyAspectStats.store_id.in_(store_ids),
            WeeklyAspectStats.week_start.in_(weeks),
            WeeklyAspectStats.aspect != OVERALL,
        )
        .group_by(WeeklyAspectStats.aspect)
    )
    return {a: (int(p), int(n), int(t)) for a, p, n, t in (await db.execute(stmt)).all()}


def _insight(ours: dict, comp: dict, has_comp: bool) -> str:
    if not has_comp:
        return "등록된 경쟁매장이 없습니다. 경쟁매장을 추가하면 비교 인사이트를 볼 수 있어요."
    worst_aspect = None
    worst_margin = 0.0
    worst_ratios = (0.0, 0.0)
    for aspect, (_op, on, ot) in ours.items():
        if aspect not in comp:
            continue
        _cp, cn, ct = comp[aspect]
        if ot == 0 or ct == 0:
            continue
        our_r, comp_r = on / ot, cn / ct
        margin = our_r - comp_r
        if margin > worst_margin:
            worst_margin, worst_aspect, worst_ratios = margin, aspect, (our_r, comp_r)
    if worst_aspect and worst_margin >= INSIGHT_MARGIN:
        our_r, comp_r = worst_ratios
        return (
            f"'{worst_aspect}'에서 경쟁매장보다 부정 비율이 높습니다 "
            f"(우리 {round(our_r * 100)}% vs 경쟁 {round(comp_r * 100)}%). 우선 개선이 필요해요."
        )
    return "전반적으로 경쟁매장보다 부정 비율이 낮거나 비슷합니다. 잘 유지하고 있어요."


async def build_compare(
    db: AsyncSession, store_id: int, range_weeks: int = 4, today: date | None = None
) -> CompareOut:
    weeks = _recent_weeks(today or _today(), range_weeks)
    ours = await _aspect_agg(db, [store_id], weeks)
    comp_ids = await _competitor_store_ids(db, store_id)
    comp = await _aspect_agg(db, comp_ids, weeks)

    aspects = [
        CompareAspect(
            aspect=a,
            ours_pos=ours.get(a, (0, 0, 0))[0],
            ours_neg=ours.get(a, (0, 0, 0))[1],
            ours_total=ours.get(a, (0, 0, 0))[2],
            comp_pos=comp.get(a, (0, 0, 0))[0],
            comp_neg=comp.get(a, (0, 0, 0))[1],
            comp_total=comp.get(a, (0, 0, 0))[2],
        )
        for a in sorted(set(ours) | set(comp))
    ]
    return CompareOut(
        range_weeks=range_weeks,
        has_competitors=bool(comp_ids),
        aspects=aspects,
        insight=_insight(ours, comp, bool(comp_ids)),
    )


def _today() -> date:
    from datetime import UTC, datetime

    return datetime.now(UTC).date()
