"""근거 진단 — 분석 결과가 원문 근거·건수·자료 충분도와 함께 나가는지 검증한다.

핵심 불변식:
- "N건 중 M건"의 M 은 근거 목록의 길이와 같고, 대시보드(weekly_aspect_stats) 수치와도 같다.
- 원문에 없는 근거 문장은 저장되지 않는다.
- 자료가 적으면 '적음'으로 표시될 뿐 점수처럼 꾸며내지 않는다.
- 검토 신호는 찾아서 보여줄 뿐 자동 제외하지 않는다. 제외는 사람이 이유와 함께 한다.
"""

from datetime import UTC, date, datetime, timedelta
from itertools import count
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.llm.schemas import (
    BatchAnalysisOut,
    Diagnosis,
    Prescription,
    ReviewAnalysisOut,
    WeeklyReportOut,
)
from app.pipeline.analyze import analyze_new_reviews
from app.pipeline.report_gen import generate_weekly_report
from app.pipeline.stats import AnalyzedReview, compute_week_stats, upsert_week_stats
from app.services.actions import list_actions
from app.services.dashboard import build_dashboard
from app.services.insights import ReviewRow, build_evidence, build_insights, find_review_checks
from app.services.review_text import long_units, normalize_text, verify_quote
from app.services.sufficiency import sufficiency_level
from tests.conftest import auth_headers

TODAY = date(2026, 6, 28)  # 일요일 → 4주 창 = 6/1(월) ~ 6/28(일), 직전 창 = 5/4 ~ 5/31
WAIT_NEG = {"category": "대기시간", "polarity": "neg"}
WAIT_POS = {"category": "대기시간", "polarity": "pos"}
TASTE_POS = {"category": "맛", "polarity": "pos"}
TASTE_NEG = {"category": "맛", "polarity": "neg"}

_seq = count()


async def _store(db, owner=None, name="근거매장"):
    store = models.Store(owner_id=owner or uuid4(), name=name)
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="naver")
    db.add(channel)
    await db.flush()
    return store, channel


async def _review(
    db,
    channel,
    body,
    written,
    aspects=(),
    *,
    keywords=(),
    rating=3,
    author="김**",
    state="analyzed",  # analyzed / pending / failed
    excluded=False,
):
    review = models.Review(
        channel_id=channel.id,
        dedup_key=f"ins-{next(_seq)}",
        body=body,
        rating=rating,
        written_at=written,
        author_masked=author,
        excluded_at=datetime.now(UTC) if excluded else None,
        exclude_reason="중복 수집" if excluded else None,
    )
    db.add(review)
    await db.flush()
    if state != "pending":
        db.add(
            models.ReviewAnalysis(
                review_id=review.id,
                sentiment="neg",
                severity="normal",
                urgent=False,
                aspects=list(aspects) if state == "analyzed" else [],
                keywords=list(keywords),
                model_ver="failed" if state == "failed" else "m",
            )
        )
        await db.flush()
    return review


# --------------------------- 순수 함수 ---------------------------
def test_verify_quote_returns_original_span_or_none():
    body = "웨이팅이 1시간 넘게 걸렸어요.\n음식은  맛있었습니다!"
    # 그대로 있는 문장
    assert verify_quote(body, "웨이팅이 1시간 넘게 걸렸어요") == "웨이팅이 1시간 넘게 걸렸어요"
    # 따옴표·끝 문장부호·공백 차이는 허용하되, 돌려주는 것은 원문 그대로의 조각
    assert verify_quote(body, '"음식은 맛있었습니다."') == "음식은  맛있었습니다"
    assert verify_quote(body, "웨이팅이1시간 넘게 걸렸어요") == "웨이팅이 1시간 넘게 걸렸어요"
    # 의역·요약은 통과하지 못한다
    assert verify_quote(body, "대기가 너무 길었다") is None
    assert verify_quote(body, "웨이팅이 2시간 넘게 걸렸어요") is None
    # 빈 값·한 글자
    assert verify_quote(body, None) is None
    assert verify_quote(body, "  ") is None
    assert verify_quote(body, "맛") is None


def test_normalize_text_and_long_units():
    assert normalize_text("맛있어요!! ㅋㅋㅋ 😊") == "맛있어요"
    assert normalize_text("Good  FOOD.") == "goodfood"

    body = "맛있어요. 사장님이 정말 친절하시고 음식도 맛있어서 또 올게요!"
    units = dict(long_units(body, 20))
    # 짧은 문장("맛있어요")은 비교 단위가 아니다. 긴 문장과 본문 전체만.
    assert "맛있어요" not in units
    assert normalize_text("사장님이 정말 친절하시고 음식도 맛있어서 또 올게요") in units
    assert normalize_text(body) in units


def test_week_stats_count_reviews_not_mentions():
    """저장된 분석에 같은 (항목, 방향)이 두 번 들어 있어도(예전 분석 데이터) 리뷰 1건으로 센다."""
    rows = {
        r.aspect: r
        for r in compute_week_stats(
            [AnalyzedReview(rating=2, sentiment="neg", aspects=[WAIT_NEG, WAIT_NEG, TASTE_POS])]
        )
    }
    assert (rows["대기시간"].neg_cnt, rows["대기시간"].total_cnt) == (1, 1)
    assert (rows["맛"].pos_cnt, rows["맛"].total_cnt) == (1, 1)


def test_sufficiency_level_thresholds():
    assert sufficiency_level(0) == "low"
    assert sufficiency_level(9) == "low"
    assert sufficiency_level(10) == "fair"
    assert sufficiency_level(29) == "fair"
    assert sufficiency_level(30) == "good"


# --------------------------- 분석: 근거 문장 원문 대조 ---------------------------
async def test_analyze_keeps_only_verified_quotes_and_dedupes_aspects(db):
    store, channel = await _store(db)
    body = "웨이팅이 1시간 넘게 걸렸어요. 직원분은 친절했어요."
    db.add(models.Review(channel_id=channel.id, dedup_key="q0", body=body, rating=2,
                         written_at=date(2026, 6, 1)))
    await db.flush()

    async def fake(prompt_name, variables, output_model):
        assert prompt_name == "classify_v2"
        return BatchAnalysisOut(results=[ReviewAnalysisOut(
            review_index=0, sentiment="neg", severity="uncomfortable", urgent=False,
            aspects=[
                {"category": "대기시간", "polarity": "neg",
                 "quote": "웨이팅이 1시간 넘게 걸렸어요"},
                # 같은 (항목, 방향) 반복 → 한 번만
                {"category": "대기시간", "polarity": "neg", "quote": "웨이팅"},
                # 원문에 없는 의역 → 인용은 버리고 항목은 유지
                {"category": "친절", "polarity": "pos", "quote": "직원이 매우 상냥했다"},
            ],
            keywords=["웨이팅"],
        )])

    assert await analyze_new_reviews(db, channel.id, generate_fn=fake) == {
        "analyzed": 1, "failed": 0,
    }
    aspects = (
        await db.execute(
            select(models.ReviewAnalysis.aspects)
            .join(models.Review, models.Review.id == models.ReviewAnalysis.review_id)
            .where(models.Review.channel_id == channel.id)
        )
    ).scalar_one()
    assert aspects == [
        {"category": "대기시간", "polarity": "neg", "quote": "웨이팅이 1시간 넘게 걸렸어요"},
        {"category": "친절", "polarity": "pos"},
    ]
    # 리뷰 1건이 '대기시간 불만'을 두 번 말해도 집계는 1건
    wait = (
        await db.execute(
            select(models.WeeklyAspectStats).where(
                models.WeeklyAspectStats.store_id == store.id,
                models.WeeklyAspectStats.aspect == "대기시간",
            )
        )
    ).scalar_one()
    assert (wait.neg_cnt, wait.total_cnt) == (1, 1)


# --------------------------- 건수 = 근거 목록 = 대시보드 ---------------------------
async def _seed_window(db):
    """이번 4주: 분석 6건(대기 불만 3 + 반대 1 + 맛 호평 2).
    분모에서 빠지는 것: 분석 전 1 / 실패 1 / 제외 1 / 날짜 없음 1.
    직전 4주: 분석 2건(대기 불만 1)."""
    store, channel = await _store(db)
    r1 = await _review(db, channel, "웨이팅이 1시간 넘게 걸렸어요. 힘들었습니다.", date(2026, 6, 3),
                       [{**WAIT_NEG, "quote": "웨이팅이 1시간 넘게 걸렸어요"}], keywords=["웨이팅"])
    r2 = await _review(db, channel, "주문이 누락돼서 30분을 더 기다렸습니다.", date(2026, 6, 16),
                       [{**WAIT_NEG, "quote": "주문이 누락돼서 30분을 더 기다렸습니다"}],
                       keywords=["웨이팅", "주문누락"])
    # 한 리뷰가 맛 호평 + 대기 불만 → 두 항목에 각각 1건
    r3 = await _review(db, channel, "맛은 좋은데 줄이 너무 길어요", date(2026, 6, 25),
                       [TASTE_POS, {**WAIT_NEG, "quote": "줄이 너무 길어요"}], keywords=["줄"])
    await _review(db, channel, "웨이팅 없이 바로 들어갔어요", date(2026, 6, 20), [WAIT_POS])
    await _review(db, channel, "음식이 정말 맛있어요", date(2026, 6, 10), [TASTE_POS])
    await _review(db, channel, "분위기가 평범해요", date(2026, 6, 11), [])
    await _review(db, channel, "아직 분석 전인 리뷰", date(2026, 6, 26), state="pending")
    await _review(db, channel, "분석에 실패한 리뷰", date(2026, 6, 26), [WAIT_NEG], state="failed")
    await _review(db, channel, "웨이팅이 1시간 넘게 걸렸어요. 힘들었습니다.", date(2026, 6, 3),
                  [WAIT_NEG], excluded=True)
    await _review(db, channel, "작성일이 없는 리뷰", None, [WAIT_NEG])
    # 직전 창
    await _review(db, channel, "지난달에도 오래 기다렸어요", date(2026, 5, 20), [WAIT_NEG])
    await _review(db, channel, "지난달 방문, 무난했어요", date(2026, 5, 21), [])
    return store, (r1, r2, r3)


async def test_insights_counts_match_evidence_and_dashboard(db):
    store, (r1, r2, r3) = await _seed_window(db)

    out = await build_insights(db, store.id, range_weeks=4, today=TODAY)

    # 분석 범위와 누락 — 어떤 리뷰가 분모에서 빠졌는지 전부 드러난다
    cov = out.coverage
    assert (cov.period_start, cov.period_end) == (date(2026, 6, 1), date(2026, 6, 28))
    assert (cov.analyzed_cnt, cov.pending_cnt, cov.failed_cnt, cov.excluded_cnt) == (6, 1, 1, 1)
    assert cov.collected_cnt == 6 + 1 + 1 + 1
    assert cov.undated_cnt == 1
    assert out.sufficiency.level == "low" and out.sufficiency.analyzed_cnt == 6

    wait = next(i for i in out.issues if i.aspect == "대기시간")
    assert (wait.related_cnt, wait.analyzed_cnt) == (3, 6)  # 실패·제외·날짜 없는 리뷰는 세지 않음
    assert wait.opposite_cnt == 1
    assert wait.weeks_mentioned == 3  # 6/1주, 6/15주, 6/22주
    assert wait.last_written_at == date(2026, 6, 25)
    assert (wait.prev_related_cnt, wait.prev_analyzed_cnt) == (1, 2)
    assert wait.enough is True
    # 미리보기 근거 문장은 최신순, 원문에 실제로 있는 문장만
    assert [q.review_id for q in wait.quotes] == [r3.id, r2.id]
    assert wait.quotes[0].quote == "줄이 너무 길어요"

    taste = next(i for i in out.strengths if i.aspect == "맛")
    assert (taste.related_cnt, taste.opposite_cnt, taste.enough) == (2, 0, False)
    assert all(i.polarity == "neg" for i in out.issues)
    assert all(i.polarity == "pos" for i in out.strengths)

    # 근거 목록의 길이 == 요약의 건수
    ev = await build_evidence(db, store.id, "대기시간", "neg", range_weeks=4, today=TODAY)
    assert ev.related_cnt == wait.related_cnt == len(ev.reviews)
    assert [r.id for r in ev.reviews] == [r3.id, r2.id, r1.id]  # 최신순
    assert ev.reviews[0].quote == "줄이 너무 길어요"
    assert all(r.quote is None or r.quote in r.body for r in ev.reviews)
    assert ev.opposite_cnt == len(ev.opposite_reviews) == 1
    assert ev.truncated is False
    assert sum(w.related_cnt for w in ev.weekly) == ev.related_cnt
    assert sum(w.analyzed_cnt for w in ev.weekly) == ev.analyzed_cnt == cov.analyzed_cnt
    assert [w.week_start for w in ev.weekly] == [
        date(2026, 6, 1), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22),
    ]
    assert [(k.keyword, k.count) for k in ev.keywords] == [
        ("웨이팅", 2), ("주문누락", 1), ("줄", 1),
    ]

    # 대시보드(사전집계)와 같은 수치
    for wk in (date(2026, 6, 1), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 22)):
        await upsert_week_stats(db, store.id, wk)
    dash = await build_dashboard(db, store.id, range_weeks=4, today=TODAY)
    assert dash.total_reviews == cov.analyzed_cnt
    assert next(a for a in dash.aspects if a.aspect == "대기시간").neg_cnt == wait.related_cnt
    assert (dash.period_start, dash.period_end) == (cov.period_start, cov.period_end)
    assert dash.sufficiency == out.sufficiency.level


async def test_as_of_moves_the_window(db):
    """as_of 를 주면 그 날짜가 속한 주까지 — 주간 리포트와 같은 4주의 근거를 볼 때 쓴다."""
    store, _ = await _seed_window(db)
    out = await build_insights(db, store.id, range_weeks=4, today=TODAY, as_of=date(2026, 5, 31))
    assert (out.coverage.period_start, out.coverage.period_end) == (
        date(2026, 5, 4), date(2026, 5, 31),
    )
    wait = next(i for i in out.issues if i.aspect == "대기시간")
    assert (wait.related_cnt, wait.analyzed_cnt) == (1, 2)
    # 미래 날짜를 주면 오늘로 고정
    future = await build_insights(db, store.id, 4, today=TODAY, as_of=date(2027, 1, 1))
    assert future.coverage.period_start == date(2026, 6, 1)


async def test_new_store_with_few_reviews_is_labeled_not_judged(db):
    """리뷰가 적은 매장은 '자료 적음'으로 표시될 뿐, 항목이 숨겨지거나 낮게 평가되지 않는다."""
    store, channel = await _store(db)
    await _review(db, channel, "음식이 식어서 나왔어요", date(2026, 6, 20), [TASTE_NEG])
    await _review(db, channel, "커피가 맛있어요", date(2026, 6, 21), [TASTE_POS])

    out = await build_insights(db, store.id, 4, today=TODAY)
    assert out.sufficiency.level == "low"
    assert (out.sufficiency.low_below, out.sufficiency.good_from) == (10, 30)
    issue = out.issues[0]
    assert (issue.aspect, issue.related_cnt, issue.analyzed_cnt) == ("맛", 1, 2)
    assert issue.enough is False and out.issue_min_related == 3

    empty_store, _ = await _store(db, name="리뷰없음")
    empty = await build_insights(db, empty_store.id, 4, today=TODAY)
    assert empty.coverage.collected_cnt == 0
    assert empty.issues == [] and empty.strengths == [] and empty.checks == []


# --------------------------- 검토 신호: 중복 기록 / 같은 문장 ---------------------------
def _row(rid, body, *, channel=1, author="김**", written=date(2026, 6, 10), excluded=False):
    return ReviewRow(
        id=rid, channel_id=channel, platform="naver" if channel == 1 else "csv",
        author_masked=author, rating=5, body=body, written_at=written, excluded=excluded,
        state="analyzed", aspects=[], keywords=[],
    )


LONG_A = "사장님이 정말 친절하시고 음식도 맛있어서 다음에 또 올게요"
LONG_B = "매장이 넓고 깨끗해서 아이들과 함께 오기 정말 좋았습니다"


def test_duplicate_record_needs_other_channel_and_compatible_author():
    checks = find_review_checks([
        # 같은 본문·같은 날짜가 네이버와 CSV 에 각각 → 같은 기록이 두 번 들어온 것으로 본다
        _row(1, "맛있어요 또 올게요", channel=1, author="김**"),
        _row(2, "맛있어요  또 올게요!", channel=2, author=None),  # CSV 에 작성자 열 없음
        # 같은 채널의 같은 문장 → 수집 단계가 이미 걸렀으니 서로 다른 사람. 짧은 문장이라 신호 없음
        _row(3, "친절해요 좋아요", channel=1, author="김**"),
        _row(4, "친절해요 좋아요", channel=1, author="김**"),
        # 채널은 다르지만 작성자 표시가 다르다 → 다른 사람
        _row(5, "분위기 좋아요 추천", channel=1, author="김**"),
        _row(6, "분위기 좋아요 추천", channel=2, author="이**"),
        # 채널·작성자가 같아도 날짜가 다르면 다른 기록
        _row(7, "가성비 좋아요 굿", channel=1, written=date(2026, 6, 11)),
        _row(8, "가성비 좋아요 굿", channel=2, written=date(2026, 6, 12)),
    ])
    assert [(c.kind, [r.id for r in c.reviews]) for c in checks] == [("duplicate_record", [1, 2])]


def test_similar_text_is_a_signal_only_for_long_sentences():
    checks = find_review_checks([
        # 서로 다른 작성 기록이 같은 긴 문장을 공유
        _row(1, LONG_A + ".", author="김**", written=date(2026, 6, 9)),
        _row(2, "두 번째 방문입니다. " + LONG_A + "!", author="이**", written=date(2026, 6, 10)),
        _row(3, LONG_A, author="박**", written=date(2026, 6, 12)),
        # 짧고 흔한 표현은 여러 명이 똑같이 써도 신호가 아니다
        _row(4, "맛있어요", author="최**"),
        _row(5, "맛있어요", author="정**"),
        # 이미 제외(처리)된 리뷰는 대상에서 빠진다
        _row(6, LONG_B, author="한**"),
        _row(7, LONG_B, author="윤**", excluded=True),
    ])
    assert len(checks) == 1
    assert checks[0].kind == "similar_text"
    assert checks[0].text == LONG_A
    assert sorted(r.id for r in checks[0].reviews) == [1, 2, 3]


def test_duplicate_record_is_not_recounted_as_similar_text():
    checks = find_review_checks([
        _row(1, LONG_A, channel=1, author="김**"),
        _row(2, LONG_A, channel=2, author="김**"),  # 1 과 같은 기록
        _row(3, LONG_A, channel=1, author="이**", written=date(2026, 6, 15)),  # 다른 사람
    ])
    assert [(c.kind, sorted(r.id for r in c.reviews)) for c in checks] == [
        ("duplicate_record", [1, 2]),
        ("similar_text", [1, 3]),  # 중복 기록은 대표 1건만 비교에 들어간다
    ]


# --------------------------- 분석 제외 (사람이 이유와 함께) ---------------------------
async def test_exclusion_endpoint_recomputes_stats_and_keeps_a_log(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store, channel = await _store(db, owner)
    today = datetime.now(UTC).date()
    week = today - timedelta(days=today.weekday())
    target = await _review(db, channel, "음식이 너무 짜고 식어서 나왔어요", today, [TASTE_NEG])
    await _review(db, channel, "직원분이 친절했어요", today,
                  [{"category": "친절", "polarity": "pos"}])
    await upsert_week_stats(db, store.id, week)

    async def _aspects():
        # 컬럼만 조회 — 세션에 캐시된 ORM 객체가 아니라 DB 의 현재 값을 본다
        stats = models.WeeklyAspectStats
        rows = (
            await db.execute(
                select(stats.aspect, stats.neg_cnt, stats.total_cnt).where(
                    stats.store_id == store.id, stats.week_start == week
                )
            )
        ).all()
        return {aspect: (neg, total) for aspect, neg, total in rows}

    assert await _aspects() == {"전체": (2, 2), "맛": (1, 1), "친절": (0, 1)}

    url = f"/api/v1/reviews/{target.id}/exclusion"
    # 이유 없이 제외할 수 없다
    assert (await client.put(url, json={"excluded": True}, headers=h)).status_code == 422
    assert (
        await client.put(url, json={"excluded": True, "reason": "   "}, headers=h)
    ).status_code == 422
    # 남의 리뷰는 404
    assert (
        await client.put(url, json={"excluded": True, "reason": "x"}, headers=auth_headers(uuid4()))
    ).status_code == 404

    res = await client.put(url, json={"excluded": True, "reason": "중복 수집"}, headers=h)
    assert res.status_code == 200
    assert res.json()["excluded"] is True and res.json()["exclude_reason"] == "중복 수집"

    # 주간 집계에서 빠지고, 0건이 된 항목 행('맛')은 남지 않는다
    assert await _aspects() == {"전체": (1, 1), "친절": (0, 1)}
    out = (await client.get(f"/api/v1/stores/{store.id}/insights", headers=h)).json()
    assert out["coverage"]["excluded_cnt"] == 1
    assert out["coverage"]["analyzed_cnt"] == 1
    assert out["issues"] == []

    # 제외 내역: 리뷰는 지워지지 않고 이유와 함께 남는다
    log = (
        await client.get(f"/api/v1/stores/{store.id}/reviews?excluded=true", headers=h)
    ).json()["items"]
    assert [(i["id"], i["excluded"], i["exclude_reason"]) for i in log] == [
        (target.id, True, "중복 수집"),
    ]
    inbox = (await client.get(f"/api/v1/stores/{store.id}/reviews", headers=h)).json()["items"]
    assert len(inbox) == 2  # 인박스에서는 숨기지 않는다

    # 다시 포함하면 원래대로
    res = await client.put(url, json={"excluded": False}, headers=h)
    assert res.json() == {
        "review_id": target.id, "excluded": False, "exclude_reason": None, "excluded_at": None,
    }
    assert await _aspects() == {"전체": (2, 2), "맛": (1, 1), "친절": (0, 1)}


async def test_competitor_review_cannot_be_excluded(client, db):
    owner = uuid4()
    my, _ = await _store(db, owner)
    comp = models.Store(owner_id=owner, name="경쟁")
    db.add(comp)
    await db.flush()
    ch = models.StoreChannel(store_id=comp.id, platform="naver", is_competitor=True,
                             competitor_of=my.id)
    db.add(ch)
    await db.flush()
    review = await _review(db, ch, "경쟁매장 리뷰", date(2026, 6, 10), [TASTE_NEG])
    res = await client.put(
        f"/api/v1/reviews/{review.id}/exclusion",
        json={"excluded": True, "reason": "빼고 싶음"}, headers=auth_headers(owner),
    )
    assert res.status_code == 400


# --------------------------- 실행 과제 + 관측 ---------------------------
async def test_action_observation_counts_before_and_after(db):
    store, channel = await _store(db)
    started = date(2026, 6, 15)
    # 실행 전 4주(5/18~6/14): 분석 5건 중 대기 불만 3건
    for d, aspects in [
        (date(2026, 5, 18), [WAIT_NEG]), (date(2026, 5, 30), [WAIT_NEG]),
        (date(2026, 6, 14), [WAIT_NEG]), (date(2026, 6, 1), [TASTE_POS]),
        (date(2026, 6, 2), []),
    ]:
        await _review(db, channel, f"실행 전 {d}", d, aspects)
    await _review(db, channel, "창 밖(더 이전)", date(2026, 5, 17), [WAIT_NEG])
    # 실행 후(6/15~6/28): 분석 6건 중 대기 불만 1건 (+ 제외 1건은 세지 않음)
    for d, aspects in [
        (date(2026, 6, 15), [WAIT_NEG]), (date(2026, 6, 16), [TASTE_POS]),
        (date(2026, 6, 20), []), (date(2026, 6, 21), [WAIT_POS]),
        (date(2026, 6, 27), [TASTE_POS]), (date(2026, 6, 28), []),
    ]:
        await _review(db, channel, f"실행 후 {d}", d, aspects)
    await _review(db, channel, "제외된 리뷰", date(2026, 6, 22), [WAIT_NEG], excluded=True)

    db.add(models.ActionItem(store_id=store.id, aspect="대기시간", polarity="neg",
                             title="예상 대기시간 안내판 설치", started_on=started))
    db.add(models.ActionItem(store_id=store.id, aspect="맛", polarity="neg",
                             title="다음 달 시작할 과제", started_on=date(2026, 7, 6),
                             status="done"))
    await db.flush()

    actions = await list_actions(db, store.id, today=TODAY)
    assert [a.title for a in actions] == ["예상 대기시간 안내판 설치", "다음 달 시작할 과제"]

    obs = actions[0].observation
    assert (obs.before_days, obs.before_related_cnt, obs.before_analyzed_cnt) == (28, 3, 5)
    assert (obs.after_days, obs.after_related_cnt, obs.after_analyzed_cnt) == (14, 1, 6)
    assert obs.enough is True and obs.min_analyzed == 5

    # 아직 실행 전인 과제는 실행 후 관측이 비어 있다
    future = actions[1].observation
    assert (future.after_days, future.after_analyzed_cnt, future.enough) == (0, 0, False)


async def test_actions_crud(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store, channel = await _store(db, owner)
    today = datetime.now(UTC).date()
    await _review(db, channel, "오래 기다렸어요", today - timedelta(days=3), [WAIT_NEG])
    await _review(db, channel, "오늘은 바로 들어갔어요", today, [WAIT_POS])

    base = f"/api/v1/stores/{store.id}/actions"
    assert (await client.get(base, headers=h)).json() == []

    payload = {"aspect": "대기시간", "title": "  예상 대기시간 안내  ", "started_on": str(today)}
    res = await client.post(base, json=payload, headers=h)
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "예상 대기시간 안내"  # 앞뒤 공백 정리
    assert (created["polarity"], created["status"], created["note"]) == ("neg", "active", None)
    obs = created["observation"]
    assert (obs["before_related_cnt"], obs["before_analyzed_cnt"]) == (1, 1)
    assert (obs["after_days"], obs["after_related_cnt"], obs["after_analyzed_cnt"]) == (1, 0, 1)
    assert obs["enough"] is False  # 실행 후 리뷰 1건 — 아직 관측하기 이르다

    # 빈 제목·알 수 없는 상태는 거부
    assert (
        await client.post(base, json={**payload, "title": "   "}, headers=h)
    ).status_code == 422
    one = f"/api/v1/actions/{created['id']}"
    assert (await client.patch(one, json={"status": "weird"}, headers=h)).status_code == 422

    res = await client.patch(one, json={"status": "done", "note": "안내판 설치 완료"}, headers=h)
    assert (res.json()["status"], res.json()["note"]) == ("done", "안내판 설치 완료")
    res = await client.patch(one, json={"note": None}, headers=h)
    assert (res.json()["status"], res.json()["note"]) == ("done", None)  # 보낸 필드만 변경

    # 소유권: 남의 매장·남의 과제는 404
    other = auth_headers(uuid4())
    assert (await client.get(base, headers=other)).status_code == 404
    assert (await client.post(base, json=payload, headers=other)).status_code == 404
    assert (await client.patch(one, json={"status": "active"}, headers=other)).status_code == 404
    assert (await client.delete(one, headers=other)).status_code == 404

    assert len((await client.get(base, headers=h)).json()) == 1
    assert (await client.delete(one, headers=h)).status_code == 204
    assert (await client.get(base, headers=h)).json() == []


# --------------------------- 엔드포인트 ---------------------------
async def test_insights_endpoints(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store, channel = await _store(db, owner)
    today = datetime.now(UTC).date()
    await _review(db, channel, "웨이팅이 1시간 넘게 걸렸어요", today,
                  [{**WAIT_NEG, "quote": "웨이팅이 1시간 넘게 걸렸어요"}])

    res = await client.get(f"/api/v1/stores/{store.id}/insights?range=8w", headers=h)
    assert res.status_code == 200
    body = res.json()
    assert body["range_weeks"] == 8
    assert body["issues"][0]["aspect"] == "대기시간"
    assert body["issues"][0]["quotes"][0]["quote"] == "웨이팅이 1시간 넘게 걸렸어요"

    res = await client.get(
        f"/api/v1/stores/{store.id}/insights/evidence",
        params={"aspect": "대기시간", "polarity": "neg", "range": "4w"}, headers=h,
    )
    assert res.status_code == 200
    ev = res.json()
    assert ev["related_cnt"] == 1 and ev["reviews"][0]["quote"] == "웨이팅이 1시간 넘게 걸렸어요"

    # 언급이 없는 항목도 200 — 0건이라고 정직하게 답한다
    none = await client.get(
        f"/api/v1/stores/{store.id}/insights/evidence",
        params={"aspect": "청결", "polarity": "neg"}, headers=h,
    )
    assert none.status_code == 200 and none.json()["related_cnt"] == 0
    # 필수 파라미터·형식
    assert (
        await client.get(f"/api/v1/stores/{store.id}/insights/evidence", headers=h)
    ).status_code == 422
    assert (
        await client.get(
            f"/api/v1/stores/{store.id}/insights/evidence",
            params={"aspect": "맛", "polarity": "bad"}, headers=h,
        )
    ).status_code == 422
    # 소유권
    other = auth_headers(uuid4())
    assert (
        await client.get(f"/api/v1/stores/{store.id}/insights", headers=other)
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/stores/{store.id}/insights/evidence", params={"aspect": "맛"}, headers=other
        )
    ).status_code == 404


# --------------------------- 리포트 → 근거 연결 ---------------------------
async def test_report_keeps_only_links_to_known_aspects(db):
    store, _ = await _store(db)
    wk = date(2026, 6, 1)
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=wk, aspect="전체",
                                    pos_cnt=6, neg_cnt=4, total_cnt=10, avg_rating=4.0))
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=wk, aspect="대기시간",
                                    pos_cnt=1, neg_cnt=3, total_cnt=4, avg_rating=2.5))
    await db.flush()

    async def fake(prompt_name, variables, output_model):
        assert prompt_name == "report_v2"
        return WeeklyReportOut(
            diagnosis=[
                Diagnosis(level="crit", title="대기 불만", evidence="부정 3건",
                          aspect="대기시간", polarity="neg"),
                # 집계에 없는 항목명 → 링크만 지운다(진단은 유지)
                Diagnosis(level="warn", title="주차 불편", evidence="부정 4건",
                          aspect="주차", polarity="neg"),
                # 방향이 빠진 링크 → 지운다
                Diagnosis(level="strength", title="전반 양호", evidence="긍정 6건",
                          aspect="대기시간"),
            ],
            prescriptions=[Prescription(title="안내", detail="대기 안내", expected_effect="기대")],
        )

    report = await generate_weekly_report(db, store.id, wk, generate_fn=fake)
    assert report.diagnosis == [
        {"level": "crit", "title": "대기 불만", "evidence": "부정 3건",
         "aspect": "대기시간", "polarity": "neg"},
        {"level": "warn", "title": "주차 불편", "evidence": "부정 4건"},
        {"level": "strength", "title": "전반 양호", "evidence": "긍정 6건"},
    ]
