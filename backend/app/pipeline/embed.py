"""리뷰 임베딩 (BGE-M3, 로컬 CPU, 1024차원). AI 비서 근거검색용.

모델은 프로세스 시작 시 1회 로딩(전역 lazy singleton) — 무겁기 때문.
FlagEmbedding 미설치 환경에서도 파이프라인이 죽지 않도록 best-effort 로 동작한다
(임베딩만 건너뜀 → 비서 근거검색 품질 저하, 나머지는 정상). 설치 시 자동 활성화.
(BACKEND.md §6, ARCHITECTURE.md §4)
"""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review, ReviewEmbedding

logger = logging.getLogger("pipeline.embed")

_model = None  # 전역 lazy singleton
_load_failed = False


def _get_model():
    """BGE-M3 모델을 1회 로딩. 실패(미설치 등)하면 None 반환하고 이후 재시도 안 함."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from FlagEmbedding import BGEM3FlagModel  # 로컬에서만 무겁게 import

        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
        logger.info("BGE-M3 로딩 완료")
    except Exception as exc:  # noqa: BLE001 - 미설치/로딩 실패는 치명적이지 않음
        _load_failed = True
        logger.warning("BGE-M3 로딩 실패 — 임베딩 건너뜀: %s", exc)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """텍스트 목록 → 1024차원 임베딩. 모델 없으면 None."""
    model = _get_model()
    if model is None:
        return None
    out = model.encode(texts, batch_size=12, max_length=1024)["dense_vecs"]
    return [vec.tolist() for vec in out]


async def embed_reviews(db: AsyncSession, review_ids: list[int]) -> int:
    """미임베딩 리뷰 본문을 임베딩해 review_embeddings 에 저장. 저장 건수 반환. (커밋은 호출자)"""
    if not review_ids:
        return 0
    stmt = select(Review.id, Review.body).where(Review.id.in_(review_ids))
    rows = (await db.execute(stmt)).all()
    if not rows:
        return 0
    vectors = embed_texts([body for _, body in rows])
    if vectors is None:
        return 0  # 모델 미가용 — best-effort 로 건너뜀

    saved = 0
    for (review_id, _), vec in zip(rows, vectors, strict=True):
        ins = (
            pg_insert(ReviewEmbedding)
            .values(review_id=review_id, embedding=vec)
            .on_conflict_do_nothing(index_elements=["review_id"])
        )
        await db.execute(ins)
        saved += 1
    return saved
