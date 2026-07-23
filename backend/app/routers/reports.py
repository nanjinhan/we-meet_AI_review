"""주간 리포트 라우터 — latest / by-id (소유 매장만)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_owned_store
from app.models import Report, Store
from app.schemas.reports import ReportRead

router = APIRouter(tags=["reports"])


@router.get("/stores/{store_id}/reports/latest", response_model=ReportRead)
async def latest_report(
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> Report:
    stmt = (
        select(Report)
        .where(Report.store_id == store.id)
        .order_by(Report.week_start.desc())
        .limit(1)
    )
    report = (await db.execute(stmt)).scalars().first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="리포트 없음")
    return report


@router.get("/stores/{store_id}/reports/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: int,
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> Report:
    report = await db.get(Report, report_id)
    if report is None or report.store_id != store.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="리포트 없음")
    return report
