"""T-02 완료 조건: 모든 모델로 insert/select 왕복.

로컬 postgres(docker-compose.dev.yml)에 마이그레이션이 적용된 상태를 전제로 한다.
전체 FK 체인을 한 번에 넣고 다시 읽어 매핑이 스키마와 일치하는지 검증한다.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app import models


async def test_full_chain_roundtrip(db):
    owner = uuid4()

    # --- 매장 ---
    store = models.Store(owner_id=owner, name="테스트카페", category="카페", address="서울")
    db.add(store)
    await db.flush()
    assert store.id is not None

    db.add(
        models.StoreSettings(
            store_id=store.id,
            tone_examples=["기존 답글1", "기존 답글2"],
            default_tone="friendly",
        )
    )

    channel = models.StoreChannel(
        store_id=store.id, platform="naver", external_url="https://m.place.naver.com/x"
    )
    db.add(channel)
    await db.flush()

    # --- 리뷰 + 분석 + 임베딩 ---
    review = models.Review(
        channel_id=channel.id,
        dedup_key="abc123",
        author_masked="김**",
        rating=2,
        body="대기시간이 너무 길었어요",
        written_at=date(2026, 7, 1),
    )
    db.add(review)
    await db.flush()

    db.add(
        models.ReviewAnalysis(
            review_id=review.id,
            sentiment="neg",
            severity="complaint",
            urgent=False,
            aspects=[{"category": "대기시간", "polarity": "neg"}],
            keywords=["대기", "느림"],
            model_ver="haiku-v1",
        )
    )
    db.add(
        models.ReviewEmbedding(review_id=review.id, embedding=[0.01] * 1024)
    )

    # --- 답글 ---
    db.add(
        models.Reply(review_id=review.id, tone="apologetic", draft="불편을 드려 죄송합니다.")
    )

    # --- 집계·리포트 ---
    db.add(
        models.WeeklyAspectStats(
            store_id=store.id,
            week_start=date(2026, 6, 29),
            aspect="대기시간",
            pos_cnt=1,
            neg_cnt=4,
            total_cnt=5,
            avg_rating=2.40,
        )
    )
    db.add(
        models.Report(
            store_id=store.id,
            week_start=date(2026, 6, 29),
            diagnosis=[{"level": "crit", "title": "대기시간", "evidence": "부정 4건"}],
            prescriptions=[{"title": "예약제", "detail": "...", "expected_effect": "..."}],
        )
    )

    # --- 알림·대화 ---
    db.add(
        models.Alert(
            store_id=store.id, review_id=review.id, kind="urgent_review", sent_via=["kakao"]
        )
    )
    db.add(models.ChatMessage(store_id=store.id, role="user", content="이번 주 어때?"))

    # --- 추가 테이블 ---
    db.add(models.CrawlJob(channel_id=channel.id, status="pending", requested_by=owner))
    db.add(
        models.KakaoToken(
            user_id=owner,
            access_token="at",
            refresh_token="rt",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.add(
        models.PushSubscription(
            user_id=owner, endpoint="https://push/x", p256dh="p", auth="a"
        )
    )

    await db.flush()

    # --- 왕복 검증 ---
    got_review = (
        await db.execute(select(models.Review).where(models.Review.id == review.id))
    ).scalar_one()
    assert got_review.author_masked == "김**"
    assert got_review.rating == 2

    got_analysis = (
        await db.execute(
            select(models.ReviewAnalysis).where(models.ReviewAnalysis.review_id == review.id)
        )
    ).scalar_one()
    assert got_analysis.sentiment == "neg"
    assert got_analysis.aspects[0]["category"] == "대기시간"
    assert got_analysis.keywords == ["대기", "느림"]

    got_emb = (
        await db.execute(
            select(models.ReviewEmbedding).where(models.ReviewEmbedding.review_id == review.id)
        )
    ).scalar_one()
    assert len(list(got_emb.embedding)) == 1024

    got_stats = (
        await db.execute(
            select(models.WeeklyAspectStats).where(
                models.WeeklyAspectStats.store_id == store.id
            )
        )
    ).scalar_one()
    assert got_stats.neg_cnt == 4


async def test_dedup_unique_constraint(db):
    """(channel_id, dedup_key) 유니크 제약 — 같은 키 재삽입 시 실패해야 한다."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    store = models.Store(owner_id=uuid4(), name="유니크테스트")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()

    db.add(models.Review(channel_id=channel.id, dedup_key="same", body="첫번째"))
    await db.flush()
    db.add(models.Review(channel_id=channel.id, dedup_key="same", body="중복"))
    with pytest.raises(IntegrityError):
        await db.flush()
