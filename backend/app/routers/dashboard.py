"""대시보드 라우터 — GET /stores/{id}/dashboard?range=4w."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_owned_store
from app.models import Store
from app.schemas.dashboard import DashboardOut
from app.services.dashboard import build_dashboard, parse_range_weeks

router = APIRouter(tags=["dashboard"])


@router.get("/stores/{store_id}/dashboard", response_model=DashboardOut)
async def get_dashboard(
    range: str = "4w",  # noqa: A002 - 스펙 쿼리명 유지
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> DashboardOut:
    return await build_dashboard(db, store.id, parse_range_weeks(range))
