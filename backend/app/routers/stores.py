"""매장·채널·설정 라우터 (BACKEND.md §9 stores.py).

라우터는 얇게 — 소유권 검사는 deps, 데이터 접근은 이 안에서 최소로.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user, get_owned_store
from app.models import CrawlJob, Store, StoreChannel, StoreSettings
from app.schemas.stores import (
    ChannelCreate,
    ChannelOut,
    CompetitorCreate,
    CompetitorOut,
    SettingsOut,
    SettingsUpdate,
    StoreCreate,
    StoreOut,
)

router = APIRouter(tags=["stores"])


@router.post("/stores", response_model=StoreOut, status_code=status.HTTP_201_CREATED)
async def create_store(
    payload: StoreCreate,
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Store:
    store = Store(
        owner_id=user,
        name=payload.name,
        category=payload.category,
        address=payload.address,
    )
    db.add(store)
    await db.flush()
    # 생성 시 store_settings row 도 함께 생성 (BACKEND.md §9)
    db.add(StoreSettings(store_id=store.id))
    await db.commit()
    return store


@router.get("/stores", response_model=list[StoreOut])
async def list_stores(
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Store]:
    # 경쟁매장도 자체 stores 행을 갖지만(통계 분리), 내 매장 목록에는 노출하지 않는다.
    competitor_stores = select(StoreChannel.store_id).where(StoreChannel.is_competitor.is_(True))
    stmt = (
        select(Store)
        .where(Store.owner_id == user, Store.id.not_in(competitor_stores))
        .order_by(Store.id)
    )
    return list((await db.execute(stmt)).scalars())


@router.get("/stores/{store_id}", response_model=StoreOut)
async def get_store(store: Store = Depends(get_owned_store)) -> Store:
    return store


@router.put("/stores/{store_id}/settings", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate,
    store: Store = Depends(get_owned_store),
    db: AsyncSession = Depends(get_db),
) -> StoreSettings:
    settings_row = await db.get(StoreSettings, store.id)
    if settings_row is None:  # 방어: 과거 데이터에 settings 가 없으면 생성
        settings_row = StoreSettings(store_id=store.id)
        db.add(settings_row)
        await db.flush()
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(settings_row, field, value)
    settings_row.updated_at = datetime.now(UTC)
    await db.commit()
    return settings_row


@router.post(
    "/stores/{store_id}/channels",
    response_model=ChannelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    payload: ChannelCreate,
    store: Store = Depends(get_owned_store),
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StoreChannel:
    # 내 매장 채널만 여기서 등록. 경쟁 채널을 내 store_id 밑에 달면 내 통계에 섞이므로 금지.
    if payload.is_competitor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="경쟁 채널은 POST /stores/{id}/competitors 로 등록하세요.",
        )
    channel = StoreChannel(
        store_id=store.id,
        platform=payload.platform,
        external_url=payload.external_url,
    )
    db.add(channel)
    await db.flush()
    # 등록 직후 첫 수집 트리거 (BACKEND.md §9). csv 는 크롤 대상이 아니고 google 은 P2.
    if payload.platform == "naver":
        db.add(CrawlJob(channel_id=channel.id, requested_by=user))
    await db.commit()
    return channel


@router.post(
    "/stores/{store_id}/competitors",
    response_model=CompetitorOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_competitor(
    payload: CompetitorCreate,
    store: Store = Depends(get_owned_store),
    user: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompetitorOut:
    """경쟁매장 등록. 경쟁매장은 **자체 stores 행**을 갖고(통계 분리), competitor_of 로 연결한다.

    경쟁 채널은 분석·집계까지만 수행되고 답글·알림은 생성되지 않는다(analyze/reply_gen 차단).
    (TECH_SPEC §5.4)
    """
    comp = Store(owner_id=user, name=payload.name)  # 경쟁매장도 자체 stores 행
    db.add(comp)
    await db.flush()
    channel = StoreChannel(
        store_id=comp.id,
        platform="naver",
        external_url=payload.external_url,
        is_competitor=True,
        competitor_of=store.id,
    )
    db.add(channel)
    await db.flush()
    db.add(CrawlJob(channel_id=channel.id, requested_by=user))  # 첫 수집 트리거
    await db.commit()
    return CompetitorOut(competitor_store_id=comp.id, channel_id=channel.id)
