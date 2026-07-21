"""내부 트리거 라우터 — 관리자 키 인증. api → worker 수동 크롤 트리거 채널.

crawl_jobs 에 pending row 를 넣으면 worker 가 10초 폴링으로 집어간다 (ARCHITECTURE §1).
데모 중 라이브 크롤 1회 시연용 (설계 원칙 3).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_internal_key
from app.models import CrawlJob, StoreChannel
from app.schemas.internal import CrawlTrigger, CrawlTriggerResult

router = APIRouter(tags=["internal"], dependencies=[Depends(require_internal_key)])


@router.post("/internal/crawl:trigger", response_model=CrawlTriggerResult)
async def trigger_crawl(
    payload: CrawlTrigger, db: AsyncSession = Depends(get_db)
) -> CrawlTriggerResult:
    channel = await db.get(StoreChannel, payload.channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="채널 없음")
    job = CrawlJob(channel_id=channel.id, requested_by=None)
    db.add(job)
    await db.commit()
    return CrawlTriggerResult(job_id=job.id, status=job.status)
