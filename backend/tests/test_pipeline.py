"""T-08 완료 조건: 리뷰 30건 → 분석 30행 + weekly_aspect_stats 정확성(수기 계산 대조), LLM mock.

+ compute_week_stats 단위 검산, 실패 배치 model_ver='failed' 처리.
"""

from datetime import date
from uuid import uuid4

from sqlalchemy import func, select

from app import models
from app.llm.schemas import BatchAnalysisOut, ReviewAnalysisOut
from app.pipeline import stats
from app.pipeline.analyze import analyze_new_reviews
from app.pipeline.stats import AnalyzedReview, compute_week_stats, week_start_of


# --------------------------- compute_week_stats (순수 함수 검산) ---------------------------
def test_compute_week_stats_hand_calc():
    reviews = [
        AnalyzedReview(rating=5, sentiment="pos", aspects=[{"category": "맛", "polarity": "pos"}]),
        AnalyzedReview(rating=1, sentiment="neg", aspects=[{"category": "맛", "polarity": "neg"}]),
        AnalyzedReview(
            rating=2,
            sentiment="neg",
            aspects=[{"category": "대기시간", "polarity": "neg"}],
        ),
        AnalyzedReview(rating=None, sentiment="neu", aspects=[]),
    ]
    rows = {r.aspect: r for r in compute_week_stats(reviews)}

    overall = rows["전체"]
    assert (overall.pos_cnt, overall.neg_cnt, overall.total_cnt) == (1, 2, 4)
    assert overall.avg_rating == 2.67  # (5+1+2)/3 = 2.666… → 2.67

    taste = rows["맛"]
    assert (taste.pos_cnt, taste.neg_cnt, taste.total_cnt) == (1, 1, 2)
    assert taste.avg_rating == 3.0  # (5+1)/2

    wait = rows["대기시간"]
    assert (wait.pos_cnt, wait.neg_cnt, wait.total_cnt) == (0, 1, 1)
    assert wait.avg_rating == 2.0
    assert "청결" not in rows  # 언급 없는 aspect 는 행 없음


# --------------------------- 통합: 30건 분석 + 집계 ---------------------------
async def _make_store_channel(db):
    store = models.Store(owner_id=uuid4(), name="분석테스트")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    return store.id, channel.id


def _fake_generate_factory():
    """배치 내 인덱스 j 로 결정론적 분석 생성 (j = 리뷰순번 % 15).

    sentiment: j 짝수 → neg, 홀수 → pos
    aspect:    j%3==0 → 맛/pos, 그 외 → 대기시간/neg
    """

    async def fake_generate(prompt_name, variables, output_model):
        results = []
        for line in variables["reviews"].splitlines():
            if not line.strip():
                continue
            j = int(line.split(".", 1)[0])
            aspects = (
                [{"category": "맛", "polarity": "pos"}]
                if j % 3 == 0
                else [{"category": "대기시간", "polarity": "neg"}]
            )
            results.append(
                ReviewAnalysisOut(
                    review_index=j,
                    sentiment="neg" if j % 2 == 0 else "pos",
                    severity="normal",
                    urgent=False,
                    aspects=aspects,
                    keywords=["키워드"],
                )
            )
        return BatchAnalysisOut(results=results)

    return fake_generate


async def test_analyze_30_reviews_and_weekly_stats(db):
    store_id, channel_id = await _make_store_channel(db)
    written = date(2026, 6, 1)
    for i in range(30):
        db.add(
            models.Review(
                channel_id=channel_id,
                dedup_key=f"k{i}",
                body=f"리뷰 본문 {i}",
                rating=(i % 5) + 1,  # 1~5 균등
                written_at=written,
            )
        )
    await db.flush()

    result = await analyze_new_reviews(db, channel_id, generate_fn=_fake_generate_factory())
    assert result == {"analyzed": 30, "failed": 0}

    # 분석 30행
    cnt = (
        await db.execute(
            select(func.count())
            .select_from(models.ReviewAnalysis)
            .join(models.Review, models.Review.id == models.ReviewAnalysis.review_id)
            .where(models.Review.channel_id == channel_id)
        )
    ).scalar_one()
    assert cnt == 30

    # weekly_aspect_stats 수기 계산 대조
    ws = week_start_of(written)
    rows = (
        await db.execute(
            select(models.WeeklyAspectStats).where(
                models.WeeklyAspectStats.store_id == store_id,
                models.WeeklyAspectStats.week_start == ws,
            )
        )
    ).scalars().all()
    by_aspect = {r.aspect: r for r in rows}

    overall = by_aspect["전체"]
    assert (overall.pos_cnt, overall.neg_cnt, overall.total_cnt) == (14, 16, 30)
    assert float(overall.avg_rating) == 3.0

    taste = by_aspect["맛"]
    assert (taste.pos_cnt, taste.neg_cnt, taste.total_cnt) == (10, 0, 10)

    wait = by_aspect["대기시간"]
    assert (wait.pos_cnt, wait.neg_cnt, wait.total_cnt) == (0, 20, 20)


async def test_reanalyze_skips_already_analyzed(db):
    _, channel_id = await _make_store_channel(db)
    db.add(models.Review(channel_id=channel_id, dedup_key="one", body="리뷰", rating=5,
                         written_at=date(2026, 6, 1)))
    await db.flush()

    fake = _fake_generate_factory()
    first = await analyze_new_reviews(db, channel_id, generate_fn=fake)
    assert first["analyzed"] == 1
    # 이미 분석된 리뷰는 다시 분석하지 않는다
    second = await analyze_new_reviews(db, channel_id, generate_fn=fake)
    assert second == {"analyzed": 0, "failed": 0}


# --------------------------- 실패 배치 처리 ---------------------------
async def test_failed_batch_marked_and_continues(db):
    _, channel_id = await _make_store_channel(db)
    for i in range(3):
        db.add(models.Review(channel_id=channel_id, dedup_key=f"f{i}", body=f"r{i}",
                             rating=3, written_at=date(2026, 6, 1)))
    await db.flush()

    async def always_fail(prompt_name, variables, output_model):
        raise RuntimeError("LLM 오류")

    result = await analyze_new_reviews(db, channel_id, generate_fn=always_fail)
    assert result == {"analyzed": 0, "failed": 3}

    # 실패도 review_analysis 행으로 마킹(model_ver='failed') → 재분석에서 다시 안 잡힘
    rows = (
        await db.execute(
            select(models.ReviewAnalysis.model_ver)
            .join(models.Review, models.Review.id == models.ReviewAnalysis.review_id)
            .where(models.Review.channel_id == channel_id)
        )
    ).scalars().all()
    assert rows == ["failed", "failed", "failed"]


async def test_duplicate_review_index_counted_once(db):
    """LLM 이 같은 review_index 를 중복으로 보내도 1건으로만 센다."""
    _, channel_id = await _make_store_channel(db)
    db.add(models.Review(channel_id=channel_id, dedup_key="d0", body="r", rating=4,
                         written_at=date(2026, 6, 1)))
    await db.flush()

    async def duplicated(prompt_name, variables, output_model):
        item = ReviewAnalysisOut(review_index=0, sentiment="pos", severity="normal",
                                 urgent=False, aspects=[], keywords=[])
        return BatchAnalysisOut(results=[item, item])  # 같은 인덱스 2번

    result = await analyze_new_reviews(db, channel_id, generate_fn=duplicated)
    assert result == {"analyzed": 1, "failed": 0}


async def test_partial_results_mark_missing_failed(db):
    """LLM 이 일부 리뷰만 분석해 오면 나머지는 failed 로 마킹한다."""
    _, channel_id = await _make_store_channel(db)
    for i in range(3):
        db.add(models.Review(channel_id=channel_id, dedup_key=f"p{i}", body=f"r{i}",
                             rating=3, written_at=date(2026, 6, 1)))
    await db.flush()

    async def only_first(prompt_name, variables, output_model):
        return BatchAnalysisOut(
            results=[ReviewAnalysisOut(review_index=0, sentiment="pos", severity="normal",
                                       urgent=False, aspects=[], keywords=[])]
        )

    result = await analyze_new_reviews(db, channel_id, generate_fn=only_first)
    assert result == {"analyzed": 1, "failed": 2}


def test_week_start_of():
    # 2026-06-03 은 수요일 → 그 주 월요일은 2026-06-01
    assert week_start_of(date(2026, 6, 3)) == date(2026, 6, 1)
    assert stats.week_start_of(date(2026, 6, 1)) == date(2026, 6, 1)  # 월요일은 그대로
