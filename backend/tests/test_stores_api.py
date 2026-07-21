"""T-04 완료 조건: 샘플 CSV 50행 업로드 → reviews 50행, 중복 재업로드 시 0행 추가.

+ stores/channels CRUD 와 소유권 404 를 API 레벨로 검증한다.
"""

from uuid import uuid4

from sqlalchemy import func, select

from app import models
from tests.conftest import auth_headers


def _sample_csv(n: int = 50) -> bytes:
    lines = ["작성일,별점,본문,작성자"]
    for i in range(n):
        day = (i % 28) + 1
        lines.append(f"2026-06-{day:02d},{(i % 5) + 1},리뷰 본문 {i}번째,고객{i}")
    return "\n".join(lines).encode("utf-8")


# --------------------------- stores CRUD ---------------------------
async def test_store_crud_and_settings_row(client, db):
    user = uuid4()
    h = auth_headers(user)

    # 생성 → 201 + store_settings row 자동 생성
    res = await client.post(
        "/api/v1/stores", json={"name": "우리매장", "category": "카페"}, headers=h
    )
    assert res.status_code == 201
    store_id = res.json()["id"]
    assert await db.get(models.StoreSettings, store_id) is not None

    # 목록/단건 조회
    res = await client.get("/api/v1/stores", headers=h)
    assert [s["id"] for s in res.json()] == [store_id]
    res = await client.get(f"/api/v1/stores/{store_id}", headers=h)
    assert res.json()["name"] == "우리매장"

    # 타 사용자는 404
    res = await client.get(f"/api/v1/stores/{store_id}", headers=auth_headers(uuid4()))
    assert res.status_code == 404

    # 미인증은 401
    res = await client.get("/api/v1/stores")
    assert res.status_code == 401

    # settings 갱신
    res = await client.put(
        f"/api/v1/stores/{store_id}/settings",
        json={"default_tone": "friendly", "tone_examples": ["감사합니다 고객님!"]},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["default_tone"] == "friendly"
    assert res.json()["tone_examples"] == ["감사합니다 고객님!"]


async def test_naver_channel_triggers_crawl_job(client, db):
    user = uuid4()
    h = auth_headers(user)
    store_id = (
        await client.post("/api/v1/stores", json={"name": "크롤매장"}, headers=h)
    ).json()["id"]

    res = await client.post(
        f"/api/v1/stores/{store_id}/channels",
        json={"platform": "naver", "external_url": "https://m.place.naver.com/restaurant/1"},
        headers=h,
    )
    assert res.status_code == 201
    channel_id = res.json()["id"]

    # 등록 직후 crawl_jobs 에 pending insert (첫 수집 트리거)
    job = (
        await db.execute(
            select(models.CrawlJob).where(models.CrawlJob.channel_id == channel_id)
        )
    ).scalar_one()
    assert job.status == "pending"
    assert job.requested_by == user

    # csv 채널은 크롤 잡을 만들지 않는다
    res = await client.post(
        f"/api/v1/stores/{store_id}/channels", json={"platform": "csv"}, headers=h
    )
    csv_channel_id = res.json()["id"]
    cnt = (
        await db.execute(
            select(func.count())
            .select_from(models.CrawlJob)
            .where(models.CrawlJob.channel_id == csv_channel_id)
        )
    ).scalar_one()
    assert cnt == 0


# --------------------------- CSV import ---------------------------
async def test_csv_import_50_rows_then_dedup(client, db):
    user = uuid4()
    h = auth_headers(user)
    store_id = (
        await client.post("/api/v1/stores", json={"name": "임포트매장"}, headers=h)
    ).json()["id"]

    files = {"file": ("reviews.csv", _sample_csv(50), "text/csv")}

    # 1차 업로드: 50행 임포트
    res = await client.post(f"/api/v1/stores/{store_id}/reviews:import", files=files, headers=h)
    assert res.status_code == 200
    assert res.json() == {"imported": 50, "skipped": 0}

    async def _count() -> int:
        return (
            await db.execute(
                select(func.count())
                .select_from(models.Review)
                .join(models.StoreChannel, models.Review.channel_id == models.StoreChannel.id)
                .where(models.StoreChannel.store_id == store_id)
            )
        ).scalar_one()

    assert await _count() == 50

    # 2차 동일 업로드: 0행 추가 (dedup)
    res = await client.post(f"/api/v1/stores/{store_id}/reviews:import", files=files, headers=h)
    assert res.json() == {"imported": 0, "skipped": 0}
    assert await _count() == 50

    # 타 사용자의 임포트 시도는 404
    res = await client.post(
        f"/api/v1/stores/{store_id}/reviews:import", files=files, headers=auth_headers(uuid4())
    )
    assert res.status_code == 404
