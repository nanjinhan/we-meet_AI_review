"""근거 진단 라우터 — 분석 결과를 원문 근거·건수·자료 충분도와 함께 내려준다.

- GET /stores/{id}/insights?range=4w           항목별 요약(문제 후보·강점) + 분석 범위 + 검토 신호
- GET /stores/{id}/insights/evidence?aspect=…  항목 하나의 근거 리뷰 원문·근거 문장·반대 의견

as_of(선택)를 주면 그 날짜가 속한 주까지를 기간으로 잡는다 — 주간 리포트 카드에서
'리포트와 같은 4주'의 근거를 열 때 쓴다.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_owned_store
from app.models import Store
from app.schemas.insights import EvidenceOut, InsightsOut
from app.services.dashboard import parse_range_weeks
from app.services.insights import build_evidence, build_insights

router = APIRouter(tags=["insights"])


@router.get("/stores/{store_id}/insights", response_model=InsightsOut)
async def get_insights(
    range: str = "4w",  # noqa: A002 - 대시보드와 같은 쿼리명 유지
    as_of: date | None = None,
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> InsightsOut:
    return await build_insights(db, store.id, parse_range_weeks(range), as_of=as_of)


@router.get("/stores/{store_id}/insights/evidence", response_model=EvidenceOut)
async def get_evidence(
    aspect: str = Query(min_length=1, max_length=30),
    polarity: Literal["pos", "neg"] = "neg",
    range: str = "4w",  # noqa: A002
    as_of: date | None = None,
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> EvidenceOut:
    return await build_evidence(
        db, store.id, aspect, polarity, parse_range_weeks(range), as_of=as_of
    )
