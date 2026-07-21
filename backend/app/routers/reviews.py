"""리뷰 라우터 — T-04 범위는 CSV 임포트만. 인박스 GET 은 T-11 에서 추가.

(BACKEND.md §9 reviews.py)
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.csv_import import parse_csv
from app.db import SessionLocal, get_db
from app.deps import get_owned_store
from app.models import Store, StoreChannel
from app.schemas.stores import ImportResult
from app.services.ingest import store_raw_reviews

logger = logging.getLogger("routers.reviews")
router = APIRouter(tags=["reviews"])


async def _analyze_channel_bg(channel_id: int) -> None:
    """업로드 응답 후 백그라운드로 분석. 요청 세션은 닫혔으므로 새 세션을 연다."""
    from app.pipeline.analyze import analyze_new_reviews

    try:
        async with SessionLocal() as db:
            await analyze_new_reviews(db, channel_id)
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - 백그라운드 실패는 요청에 영향 없음
        logger.warning("CSV 임포트 후 분석 실패(channel=%s): %s", channel_id, exc)


@router.post("/stores/{store_id}/reviews:import", response_model=ImportResult)
async def import_reviews(
    background_tasks: BackgroundTasks,
    store: Store = Depends(get_owned_store),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    raws, skipped = parse_csv(await file.read())

    # CSV 채널 find-or-create (매장당 1개)
    stmt = select(StoreChannel).where(
        StoreChannel.store_id == store.id, StoreChannel.platform == "csv"
    )
    channel = (await db.execute(stmt)).scalars().first()
    if channel is None:
        channel = StoreChannel(store_id=store.id, platform="csv")
        db.add(channel)
        await db.flush()

    # on conflict do nothing 으로 중복(dedup_key) 자동 스킵 — 재업로드 시 0행 추가
    imported = await store_raw_reviews(db, channel.id, raws)
    await db.commit()

    # 업로드 후 분석 파이프라인을 백그라운드로 실행 (BACKEND.md §9)
    background_tasks.add_task(_analyze_channel_bg, channel.id)
    return ImportResult(imported=imported, skipped=skipped)
