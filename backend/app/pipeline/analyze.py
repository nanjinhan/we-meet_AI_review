"""리뷰 분석 파이프라인 (worker·api 양쪽에서 호출).

신규 리뷰를 배치로 LLM 분류 → review_analysis 저장 → 주간 집계 UPSERT →
(경쟁매장이 아니면) urgent/저평점 알림 → 임베딩. 실패 배치는 model_ver='failed' 로
마킹하고 계속(전체 중단 금지).
(BACKEND.md §6, ARCHITECTURE.md §4, TECH_SPEC §5.1)
"""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.schemas import BatchAnalysisOut
from app.models import Review, ReviewAnalysis, StoreChannel
from app.pipeline import embed, stats

logger = logging.getLogger("pipeline.analyze")

GenerateFn = Callable[..., Awaitable[BatchAnalysisOut]]

# 저평점 기준: 이 값 이하면 즉시 알림 대상 (TECH_SPEC §5.1)
LOW_RATING_THRESHOLD = 2


async def _default_generate(prompt_name: str, variables: dict, output_model: type):
    # 지연 import — 테스트에서 generate_fn 주입 시 LLM 클라이언트를 건드리지 않는다
    from app.llm.client import generate

    return await generate(
        prompt_name, variables, output_model, model=settings.llm_model_classify
    )


def _format_batch(reviews: list[Review]) -> str:
    return "\n".join(f"{i}. {r.body}" for i, r in enumerate(reviews))


async def _insert_analysis(db: AsyncSession, review_id: int, values: dict) -> None:
    ins = (
        pg_insert(ReviewAnalysis)
        .values(review_id=review_id, **values)
        .on_conflict_do_nothing(index_elements=["review_id"])
    )
    await db.execute(ins)


async def _mark_failed(db: AsyncSession, reviews: list[Review]) -> None:
    for r in reviews:
        await _insert_analysis(db, r.id, {"model_ver": "failed"})


async def analyze_new_reviews(
    db: AsyncSession,
    channel_id: int,
    *,
    generate_fn: GenerateFn = _default_generate,
    batch_size: int = 15,
) -> dict[str, int]:
    """채널의 미분석 리뷰를 분석. {"analyzed": n, "failed": m} 반환. (커밋은 호출자)"""
    channel = await db.get(StoreChannel, channel_id)
    if channel is None:
        return {"analyzed": 0, "failed": 0}

    stmt = (
        select(Review)
        .outerjoin(ReviewAnalysis, ReviewAnalysis.review_id == Review.id)
        .where(Review.channel_id == channel_id, ReviewAnalysis.review_id.is_(None))
        .order_by(Review.id)
    )
    pending = list((await db.execute(stmt)).scalars())
    if not pending:
        return {"analyzed": 0, "failed": 0}

    analyzed_ids: list[int] = []
    urgent_reviews: list[Review] = []
    affected_weeks: set = set()
    failed = 0

    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        try:
            result = await generate_fn(
                "classify_v1", {"reviews": _format_batch(batch)}, BatchAnalysisOut
            )
        except Exception as exc:  # noqa: BLE001 - 실패 배치는 마킹 후 계속
            logger.warning("분석 배치 실패(channel=%s): %s", channel_id, exc)
            await _mark_failed(db, batch)
            failed += len(batch)
            continue

        covered: set[int] = set()
        for item in result.results:
            if not 0 <= item.review_index < len(batch):
                continue  # LLM 이 잘못된 인덱스를 주면 무시
            if item.review_index in covered:
                continue  # 중복 인덱스 무시 — 카운트/임베딩 목록 왜곡 방지
            review = batch[item.review_index]
            covered.add(item.review_index)
            await _insert_analysis(
                db,
                review.id,
                {
                    "sentiment": item.sentiment,
                    "severity": item.severity,
                    "urgent": item.urgent,
                    "aspects": [a.model_dump() for a in item.aspects],
                    "keywords": item.keywords,
                    "model_ver": settings.llm_model_classify,
                },
            )
            analyzed_ids.append(review.id)
            wd = review.written_at or review.collected_at.date()
            affected_weeks.add(stats.week_start_of(wd))
            if item.urgent or (review.rating is not None and review.rating <= LOW_RATING_THRESHOLD):
                urgent_reviews.append(review)

        # 결과가 누락된 리뷰는 failed 로 마킹(무한 재시도 방지)
        missing = [b for i, b in enumerate(batch) if i not in covered]
        if missing:
            await _mark_failed(db, missing)
            failed += len(missing)

    # 주간 집계 UPSERT
    for week in affected_weeks:
        await stats.upsert_week_stats(db, channel.store_id, week)

    # 경쟁매장은 analyze/stats/embed 까지만 — 알림·답글 생성 금지 (TECH_SPEC §4.2)
    if not channel.is_competitor and urgent_reviews:
        await _dispatch_urgent(db, channel.store_id, urgent_reviews)

    await _embed_safe(db, analyzed_ids)
    return {"analyzed": len(analyzed_ids), "failed": failed}


async def _dispatch_urgent(db: AsyncSession, store_id: int, reviews: list[Review]) -> None:
    """긴급/저평점 즉시 알림. T-10 에서 notify/dispatch 가 추가되면 자동 연결된다."""
    try:
        from app.notify import dispatch  # noqa: PLC0415 - T-10 전까지는 없음
    except ImportError:
        logger.debug("notify 미연결 (T-10): 긴급 리뷰 %d건 보류", len(reviews))
        return
    for review in reviews:
        await dispatch.send_urgent(db, store_id, review)


async def _embed_safe(db: AsyncSession, review_ids: list[int]) -> None:
    try:
        await embed.embed_reviews(db, review_ids)
    except Exception as exc:  # noqa: BLE001 - 임베딩 실패는 파이프라인을 막지 않는다
        logger.warning("임베딩 실패(건너뜀): %s", exc)
