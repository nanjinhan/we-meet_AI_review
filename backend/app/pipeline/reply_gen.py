"""AI 답글 초안 생성.

리뷰 본문 + 분석 결과 + 사장님 톤 프로필(store_settings.tone_examples few-shot) + 선택 톤
→ generate("reply_v1", ..., ReplyOut) → replies insert(status='draft').
가드레일(보상 약속 금지 등)은 프롬프트 파일 reply_v1.md 에 명시돼 있다.
(BACKEND.md §6, TECH_SPEC §5.2)
"""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.schemas import ReplyOut
from app.models import Reply, Review, ReviewAnalysis, StoreChannel, StoreSettings

logger = logging.getLogger("pipeline.reply_gen")

GenerateFn = Callable[..., Awaitable[ReplyOut]]


async def _default_generate(prompt_name: str, variables: dict, output_model: type) -> ReplyOut:
    from app.llm.client import generate  # 지연 import (생성 모델 기본값 사용)

    return await generate(prompt_name, variables, output_model)


def _analysis_summary(analysis: ReviewAnalysis | None) -> str:
    if analysis is None or analysis.model_ver == "failed":
        return "(분석 없음)"
    aspects = ", ".join(f"{a['category']}({a['polarity']})" for a in (analysis.aspects or []))
    return (
        f"감정={analysis.sentiment}, 심각도={analysis.severity}, "
        f"항목=[{aspects}], 키워드={list(analysis.keywords or [])}"
    )


async def generate_reply(
    db: AsyncSession,
    review_id: int,
    tone: str,
    *,
    generate_fn: GenerateFn = _default_generate,
) -> Reply:
    """리뷰에 대한 답글 초안을 생성해 replies 에 저장. 기존 draft 는 discard 후 재생성.

    (커밋은 호출자) 반환: 새 Reply(status='draft').
    """
    review = await db.get(Review, review_id)
    if review is None:
        raise ValueError(f"리뷰 없음: {review_id}")

    analysis = await db.get(ReviewAnalysis, review_id)
    channel = await db.get(StoreChannel, review.channel_id)
    if channel is not None and channel.is_competitor:
        # 경쟁매장 채널은 분석까지만 — 답글 생성 금지 (TECH_SPEC §4.2, BACKEND.md §6)
        raise ValueError("경쟁매장 리뷰에는 답글을 생성할 수 없습니다.")
    settings_row = await db.get(StoreSettings, channel.store_id) if channel else None
    tone_examples = list(settings_row.tone_examples) if settings_row else []

    out = await generate_fn(
        "reply_v1",
        {
            "review_body": review.body,
            "analysis": _analysis_summary(analysis),
            "tone": tone,
            "tone_examples": "\n".join(f"- {ex}" for ex in tone_examples) or "(없음)",
        },
        ReplyOut,
    )

    # 기존 draft 는 discard (재생성 시 초안이 중복되지 않게)
    await db.execute(
        update(Reply)
        .where(Reply.review_id == review_id, Reply.status == "draft")
        .values(status="discarded")
    )

    reply = Reply(review_id=review_id, tone=tone, draft=out.draft, status="draft")
    db.add(reply)
    await db.flush()
    return reply
