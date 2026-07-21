"""T-11 완료 조건: 점수 산식 단위 테스트 + 커서 경계(마지막 페이지) 테스트.

+ 인박스 필터, 대시보드 집계.
"""

from datetime import date
from uuid import uuid4

from app import models
from app.services.dashboard import build_dashboard, parse_range_weeks
from app.services.score import composite_score
from tests.conftest import auth_headers


# --------------------------- 점수 산식 (완료 조건) ---------------------------
def test_composite_score():
    assert composite_score(1.0, 5.0, 1.0) == 100.0  # 0.5+0.3+0.2
    assert composite_score(0.0, None, 0.0) == 0.0
    assert composite_score(0.6, 4.0, 0.0) == 54.0  # 0.3 + 0.24
    assert composite_score(0.5, 4.0, 0.25) == 54.0  # 0.25 + 0.24 + 0.05


def test_parse_range_weeks():
    assert parse_range_weeks("4w") == 4
    assert parse_range_weeks("12w") == 12
    assert parse_range_weeks("99w") == 12  # 클램프
    assert parse_range_weeks("bad") == 4


# --------------------------- 인박스 커서 페이지네이션 ---------------------------
async def _seed_inbox(db, owner) -> tuple[int, list[int]]:
    store = models.Store(owner_id=owner, name="인박스")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    ids = []
    for i in range(5):
        r = models.Review(channel_id=channel.id, dedup_key=f"i{i}", body=f"리뷰{i}",
                          rating=(i % 5) + 1, written_at=date(2026, 6, 1))
        db.add(r)
        await db.flush()
        ids.append(r.id)
        db.add(models.ReviewAnalysis(
            review_id=r.id, sentiment=("neg" if i % 2 == 0 else "pos"), severity="normal",
            urgent=(i == 0), aspects=[], keywords=[], model_ver="m",
        ))
    # reviews[1] 에 승인된 답글 → answered
    db.add(models.Reply(review_id=ids[1], tone="polite", draft="답글", status="approved"))
    await db.flush()
    return store.id, ids


async def test_reviews_cursor_pagination_boundary(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store_id, ids = await _seed_inbox(db, owner)  # ids 오름차순, 응답은 id desc

    url = f"/api/v1/stores/{store_id}/reviews"
    p1 = (await client.get(f"{url}?limit=2", headers=h)).json()
    assert [it["id"] for it in p1["items"]] == [ids[4], ids[3]]
    assert p1["next_cursor"] == ids[3]

    p2 = (await client.get(f"{url}?limit=2&cursor={ids[3]}", headers=h)).json()
    assert [it["id"] for it in p2["items"]] == [ids[2], ids[1]]
    assert p2["next_cursor"] == ids[1]

    p3 = (await client.get(f"{url}?limit=2&cursor={ids[1]}", headers=h)).json()
    assert [it["id"] for it in p3["items"]] == [ids[0]]
    assert p3["next_cursor"] is None  # 마지막 페이지 경계


async def test_reviews_filters(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store_id, ids = await _seed_inbox(db, owner)
    url = f"/api/v1/stores/{store_id}/reviews"

    neg = (await client.get(f"{url}?sentiment=neg", headers=h)).json()
    assert {it["id"] for it in neg["items"]} == {ids[0], ids[2], ids[4]}

    urg = (await client.get(f"{url}?urgent=true", headers=h)).json()
    assert [it["id"] for it in urg["items"]] == [ids[0]]

    ans = (await client.get(f"{url}?answered=true", headers=h)).json()
    assert [it["id"] for it in ans["items"]] == [ids[1]]
    assert ans["items"][0]["answered"] is True
    assert ans["items"][0]["reply_draft"] == "답글"

    unans = (await client.get(f"{url}?answered=false", headers=h)).json()
    assert ids[1] not in {it["id"] for it in unans["items"]}

    # 타 사용자는 404
    assert (await client.get(url, headers=auth_headers(uuid4()))).status_code == 404


# --------------------------- 대시보드 집계 ---------------------------
async def test_build_dashboard_score_and_shape(db):
    owner = uuid4()
    store = models.Store(owner_id=owner, name="대시매장")
    db.add(store)
    await db.flush()
    wk = date(2026, 6, 1)  # 월요일
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=wk, aspect="전체",
                                    pos_cnt=6, neg_cnt=4, total_cnt=10, avg_rating=4.0))
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=wk, aspect="맛",
                                    pos_cnt=3, neg_cnt=1, total_cnt=4, avg_rating=4.5))
    await db.flush()

    out = await build_dashboard(db, store.id, range_weeks=4, today=date(2026, 6, 1))
    assert out.score == 54.0  # 100*(0.5*0.6 + 0.3*0.8 + 0.2*0)
    assert out.positive_ratio == 0.6
    assert out.avg_rating == 4.0
    assert out.answer_rate == 0.0  # 기간 내 리뷰 0건
    assert out.total_reviews == 10
    assert out.score_delta is None  # 직전 기간 데이터 없음
    assert len(out.trend) == 4  # 4주 (빈 주는 0)
    assert any(a.aspect == "맛" for a in out.aspects)


async def test_dashboard_endpoint_smoke(client, db):
    owner = uuid4()
    store = models.Store(owner_id=owner, name="빈대시")
    db.add(store)
    await db.flush()
    res = await client.get(
        f"/api/v1/stores/{store.id}/dashboard?range=4w", headers=auth_headers(owner)
    )
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["score"], int | float)
    assert body["range_weeks"] == 4
