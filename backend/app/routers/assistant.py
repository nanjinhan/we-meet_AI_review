"""AI 비서 라우터 — 하이브리드(라우터 → 템플릿 쿼리 → 답변 스트리밍).

흐름 (ARCHITECTURE §4):
  질문 → 라우터 LLM(RouterDecision) → intent별 템플릿 쿼리 → 조회 결과를 컨텍스트로 답변(SSE)
  → chat_messages 저장. 조회 결과가 비면 LLM(답변) 미호출 + "데이터 부족" 정형 응답(환각 금지).

주: 답변은 route 함수에서 스트림을 모두 소비해 저장까지 마친 뒤 SSE 로 재전송한다 —
StreamingResponse 제너레이터 안에서 요청 DB 세션을 쓰면 세션이 닫혀 있어 실패하기 때문.
(BACKEND.md §9/§10, TECH_SPEC §5.5)
"""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.deps import get_owned_store
from app.llm import client as llm_client
from app.llm.schemas import RouterDecision
from app.models import ChatMessage, Store
from app.schemas.assistant import AssistantIn, ChatMessageOut
from app.services.assistant_queries import (
    aspect_trend,
    compare_period,
    search_evidence,
    top_problem_aspects,
)

logger = logging.getLogger("routers.assistant")
router = APIRouter(tags=["assistant"])

FIXED_NO_DATA = "해당 기간의 데이터가 부족해요. 리뷰가 더 쌓이면 분석해 드릴게요."


async def _route(question: str) -> RouterDecision:
    return await llm_client.generate(
        "assistant_router_v1", {"question": question}, RouterDecision,
        model=settings.llm_model_classify,
    )


async def _gather_context(
    db: AsyncSession, store_id: int, d: RouterDecision, question: str
) -> tuple[str, bool]:
    parts: list[str] = []
    has_data = False

    if d.intent in ("stats", "both"):
        if d.aspect:
            trend = await aspect_trend(db, store_id, d.aspect, d.period_weeks)
            if trend:
                has_data = True
                cmp = await compare_period(db, store_id, d.aspect, d.period_weeks)
                parts.append(f"[{d.aspect} 추이] " + json.dumps(trend, ensure_ascii=False))
                parts.append(f"[{d.aspect} 전기간대비] " + json.dumps(cmp, ensure_ascii=False))
        else:
            tops = await top_problem_aspects(db, store_id, d.period_weeks)
            if tops:
                has_data = True
                parts.append("[문제 항목 상위] " + json.dumps(tops, ensure_ascii=False))

    if d.intent in ("evidence", "both"):
        reviews = await search_evidence(
            db, store_id, d.query_text or question, d.sentiment, d.period_weeks
        )
        if reviews:
            has_data = True
            parts.append(
                "[관련 리뷰]\n"
                + "\n".join(f"- ({r.rating}점) {r.body[:80]}" for r in reviews)
            )

    return "\n".join(parts), has_data


async def _answer_tokens(question: str, context: str) -> list[str]:
    tokens: list[str] = []
    async for tok in llm_client.generate_stream(
        "assistant_answer_v1", {"question": question, "context": context}
    ):
        tokens.append(tok)
    return tokens


@router.post("/stores/{store_id}/assistant/messages")
async def assistant_message(
    payload: AssistantIn,
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    db.add(ChatMessage(store_id=store.id, role="user", content=payload.message))

    decision = await _route(payload.message)
    context, has_data = await _gather_context(db, store.id, decision, payload.message)

    if decision.intent in ("stats", "evidence", "both") and not has_data:
        tokens = [FIXED_NO_DATA]  # 데이터 0건 → 답변 LLM 미호출 (환각 방지)
    else:
        tokens = await _answer_tokens(payload.message, context)

    answer = "".join(tokens)
    db.add(ChatMessage(store_id=store.id, role="assistant", content=answer))
    await db.commit()

    async def sse():
        for tok in tokens:
            yield f"data: {tok.replace(chr(10), ' ')}\n\n"  # SSE 프레이밍: 개행 제거
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


@router.get("/stores/{store_id}/assistant/messages", response_model=list[ChatMessageOut])
async def assistant_history(
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.store_id == store.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return list((await db.execute(stmt)).scalars())
