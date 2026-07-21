"""RawReview → reviews 저장 (CSV 임포트 라우터와 크롤 워커가 공유).

작성자 원문은 여기서 마스킹되어 저장된다(원문 표시명 미저장, TECH_SPEC §3.4).
중복은 (channel_id, dedup_key) 유니크 + ON CONFLICT DO NOTHING 으로 자동 스킵.
커밋은 호출자 책임 — 이 함수는 flush 까지만 한다.
"""

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import RawReview, dedup_key, mask_author
from app.models import Review


async def store_raw_reviews(
    db: AsyncSession, channel_id: int, raws: list[RawReview]
) -> int:
    """신규 저장 건수 반환. 이미 존재하는 dedup_key 는 건너뛴다."""
    imported = 0
    for r in raws:
        ins = (
            pg_insert(Review)
            .values(
                channel_id=channel_id,
                dedup_key=dedup_key(r),
                author_masked=mask_author(r.author_display) or None,
                rating=r.rating,
                body=r.body,
                written_at=r.visited_at,
            )
            .on_conflict_do_nothing(index_elements=["channel_id", "dedup_key"])
            .returning(Review.id)
        )
        if (await db.execute(ins)).scalar_one_or_none() is not None:
            imported += 1
    return imported
