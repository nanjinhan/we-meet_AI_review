"""T-13 완료 조건: 경쟁 채널 리뷰는 분석·집계되지만 replies/alerts 가 생기지 않는다.

+ GET /compare (우리 vs 경쟁 aspect + 인사이트).
"""

from datetime import date
from uuid import uuid4

from sqlalchemy import func, select

from app import models
from app.llm.schemas import BatchAnalysisOut, ReviewAnalysisOut
from app.pipeline.analyze import analyze_new_reviews
from app.services.compare import build_compare
from tests.conftest import auth_headers

WK = date(2026, 6, 1)


# --------------------------- 완료 조건: 경쟁 채널 답글·알림 미생성 ---------------------------
async def test_competitor_channel_analyzed_but_no_replies_no_alerts(db):
    owner = uuid4()
    my = models.Store(owner_id=owner, name="우리매장")
    db.add(my)
    await db.flush()
    comp = models.Store(owner_id=owner, name="경쟁A")
    db.add(comp)
    await db.flush()
    ch = models.StoreChannel(
        store_id=comp.id, platform="naver", is_competitor=True, competitor_of=my.id
    )
    db.add(ch)
    await db.flush()
    for i in range(3):
        db.add(models.Review(channel_id=ch.id, dedup_key=f"c{i}", body="이물질이 나왔어요",
                            rating=1, written_at=WK))  # urgent 유발 조건
    await db.flush()

    async def fake(prompt_name, variables, output_model):
        res = []
        for line in variables["reviews"].splitlines():
            if not line.strip():
                continue
            j = int(line.split(".", 1)[0])
            res.append(ReviewAnalysisOut(
                review_index=j, sentiment="neg", severity="complaint", urgent=True,
                aspects=[{"category": "청결", "polarity": "neg"}], keywords=["이물질"],
            ))
        return BatchAnalysisOut(results=res)

    result = await analyze_new_reviews(db, ch.id, generate_fn=fake)
    assert result["analyzed"] == 3

    # 분석·집계는 수행됨
    an = (
        await db.execute(
            select(func.count())
            .select_from(models.ReviewAnalysis)
            .join(models.Review, models.Review.id == models.ReviewAnalysis.review_id)
            .where(models.Review.channel_id == ch.id)
        )
    ).scalar_one()
    assert an == 3
    stats = (
        await db.execute(
            select(func.count())
            .select_from(models.WeeklyAspectStats)
            .where(models.WeeklyAspectStats.store_id == comp.id)
        )
    ).scalar_one()
    assert stats > 0  # 경쟁매장 자체 store_id 로 통계 분리 저장

    # 답글·알림은 생성되지 않음 (경쟁 채널)
    alerts = (
        await db.execute(
            select(func.count())
            .select_from(models.Alert)
            .where(models.Alert.store_id.in_([my.id, comp.id]))
        )
    ).scalar_one()
    assert alerts == 0
    replies = (
        await db.execute(
            select(func.count())
            .select_from(models.Reply)
            .join(models.Review, models.Review.id == models.Reply.review_id)
            .where(models.Review.channel_id == ch.id)
        )
    ).scalar_one()
    assert replies == 0


# --------------------------- GET /compare ---------------------------
async def _seed_compare(db, owner) -> int:
    my = models.Store(owner_id=owner, name="우리매장")
    db.add(my)
    await db.flush()
    comp = models.Store(owner_id=owner, name="경쟁A")
    db.add(comp)
    await db.flush()
    db.add(models.StoreChannel(
        store_id=comp.id, platform="naver", is_competitor=True, competitor_of=my.id
    ))
    # 대기시간: 우리 부정 4/5(80%) vs 경쟁 1/4(25%) → 우리가 열세
    db.add(models.WeeklyAspectStats(store_id=my.id, week_start=WK, aspect="대기시간",
                                    pos_cnt=1, neg_cnt=4, total_cnt=5, avg_rating=2.0))
    db.add(models.WeeklyAspectStats(store_id=comp.id, week_start=WK, aspect="대기시간",
                                    pos_cnt=3, neg_cnt=1, total_cnt=4, avg_rating=4.0))
    await db.flush()
    return my.id


async def test_build_compare_ours_vs_competitor(db):
    store_id = await _seed_compare(db, uuid4())
    out = await build_compare(db, store_id, range_weeks=4, today=WK)
    assert out.has_competitors is True
    wait = next(a for a in out.aspects if a.aspect == "대기시간")
    assert (wait.ours_pos, wait.ours_neg, wait.ours_total) == (1, 4, 5)
    assert (wait.comp_pos, wait.comp_neg, wait.comp_total) == (3, 1, 4)
    assert "대기시간" in out.insight  # 열세 항목을 인사이트로 지목


async def test_compare_no_competitors(db):
    owner = uuid4()
    store = models.Store(owner_id=owner, name="경쟁없음")
    db.add(store)
    await db.flush()
    out = await build_compare(db, store.id, range_weeks=4, today=WK)
    assert out.has_competitors is False
    assert "경쟁매장" in out.insight


async def test_compare_endpoint(client, db):
    owner = uuid4()
    store_id = await _seed_compare(db, owner)
    res = await client.get(
        f"/api/v1/stores/{store_id}/compare?range=4w", headers=auth_headers(owner)
    )
    assert res.status_code == 200
    assert res.json()["has_competitors"] is True
    # 타 사용자 404
    assert (
        await client.get(f"/api/v1/stores/{store_id}/compare", headers=auth_headers(uuid4()))
    ).status_code == 404


# ---------------- 검토 회귀: 경쟁매장 등록 플로우 / 목록 누출 / 채널 오용 방지 ----------------
async def test_add_competitor_creates_own_store_and_hidden_from_list(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store = (
        await client.post("/api/v1/stores", json={"name": "우리매장"}, headers=h)
    ).json()

    res = await client.post(
        f"/api/v1/stores/{store['id']}/competitors",
        json={"name": "경쟁A", "external_url": "https://m.place.naver.com/x"},
        headers=h,
    )
    assert res.status_code == 201
    body = res.json()
    comp_store_id = body["competitor_store_id"]
    assert comp_store_id != store["id"]

    # 경쟁 채널은 competitor_of 로 연결 + is_competitor
    ch = await db.get(models.StoreChannel, body["channel_id"])
    assert ch.is_competitor is True
    assert ch.competitor_of == store["id"]
    assert ch.store_id == comp_store_id
    # 첫 수집 트리거(crawl_jobs) 생성
    from sqlalchemy import select as _select

    jobs = (
        await db.execute(
            _select(func.count()).select_from(models.CrawlJob).where(
                models.CrawlJob.channel_id == ch.id
            )
        )
    ).scalar_one()
    assert jobs == 1

    # 경쟁매장은 내 매장 목록에 노출되지 않는다
    listed = (await client.get("/api/v1/stores", headers=h)).json()
    assert [s["id"] for s in listed] == [store["id"]]


async def test_channels_reject_competitor(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store = (await client.post("/api/v1/stores", json={"name": "우리"}, headers=h)).json()
    # 내 매장 채널 엔드포인트로 경쟁 채널 등록 시도 → 400 (통계 오염 방지)
    res = await client.post(
        f"/api/v1/stores/{store['id']}/channels",
        json={"platform": "naver", "external_url": "https://x", "is_competitor": True},
        headers=h,
    )
    assert res.status_code == 400
