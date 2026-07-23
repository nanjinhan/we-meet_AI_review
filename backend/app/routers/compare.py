"""경쟁매장 비교 라우터 — GET /stores/{id}/compare?range=4w."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_owned_store
from app.models import Store
from app.schemas.compare import CompareOut
from app.services.compare import build_compare
from app.services.dashboard import parse_range_weeks

router = APIRouter(tags=["compare"])


@router.get("/stores/{store_id}/compare", response_model=CompareOut)
async def get_compare(
    range: str = "4w",  # noqa: A002 - 스펙 쿼리명 유지
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> CompareOut:
    return await build_compare(db, store.id, parse_range_weeks(range))
