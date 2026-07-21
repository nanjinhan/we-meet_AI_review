"""답글 라우터 — 생성 / 승인 (반자동 게시).

승인은 status='approved' 로만 바꾸고 draft 를 응답에 담는다. 프론트가 클립보드 복사 +
스마트플레이스 답글창 딥링크를 연다. **서버는 네이버에 아무것도 게시하지 않는다**
(CLAUDE.md 규칙 7, TECH_SPEC §5.2).
(BACKEND.md §9)
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_owned_reply, get_owned_review
from app.models import Reply, Review
from app.pipeline.reply_gen import generate_reply
from app.schemas.replies import ReplyGenerateIn, ReplyRead

router = APIRouter(tags=["replies"])


@router.post("/reviews/{review_id}/reply:generate", response_model=ReplyRead)
async def generate_reply_endpoint(
    payload: ReplyGenerateIn,
    review: Review = Depends(get_owned_review),
    db: AsyncSession = Depends(get_db),
) -> Reply:
    """AI 답글 초안 생성(동기, 수 초). 기존 draft 있으면 discard 후 재생성."""
    try:
        reply = await generate_reply(db, review.id, payload.tone)
    except ValueError as exc:  # 경쟁매장 리뷰 등 생성 불가 케이스
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await db.commit()
    return reply


@router.post("/replies/{reply_id}:approve", response_model=ReplyRead)
async def approve_reply(
    reply: Reply = Depends(get_owned_reply),
    db: AsyncSession = Depends(get_db),
) -> Reply:
    """답글 승인. status='approved' + approved_at. 응답의 draft 를 프론트가 클립보드 복사.

    폐기된(discarded) 초안은 승인 불가 — 재생성으로 대체된 옛 초안이 되살아나는 것 방지.
    이미 승인된 답글의 재승인은 멱등(기존 approved_at 유지).
    """
    if reply.status == "discarded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="폐기된 초안은 승인할 수 없습니다. 답글을 다시 생성하세요.",
        )
    if reply.status != "approved":
        reply.status = "approved"
        reply.approved_at = datetime.now(UTC)
        await db.commit()
    return reply
