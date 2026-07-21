"""T-06 완료 조건: crawl_jobs pending insert → 워커가 집어 done 처리 (수집기 mock).

+ 실패→failed, 백오프 재시도, 0건 2연속 자가진단, /internal/crawl:trigger 를 검증한다.
"""

from datetime import date
from uuid import uuid4

from sqlalchemy import func, select

from app import models
from app.collectors.base import BaseCollector, RawReview
from app.worker import (
    _run_with_backoff,
    enqueue_scheduled_crawls,
    is_structure_change_suspected,
    process_pending_jobs,
    run_crawl_job,
)


class FakeCollector(BaseCollector):
    """미리 정한 리뷰를 돌려주거나, fail_times 번 예외를 던진 뒤 성공한다."""

    def __init__(self, reviews: list[RawReview], fail_times: int = 0):
        self._reviews = reviews
        self._fail_times = fail_times
        self.calls = 0

    async def collect(self, channel, stop_after_known=2, known_keys=None):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("셀렉터 깨짐 시뮬레이션")
        return self._reviews


async def _make_channel(session_factory, platform="naver") -> tuple[int, int]:
    """store + channel 생성, (store_id, channel_id) 반환."""
    async with session_factory() as db:
        store = models.Store(owner_id=uuid4(), name="워커테스트")
        db.add(store)
        await db.flush()
        channel = models.StoreChannel(store_id=store.id, platform=platform)
        db.add(channel)
        await db.flush()
        await db.commit()
        return store.id, channel.id


async def _add_job(session_factory, channel_id: int) -> int:
    async with session_factory() as db:
        job = models.CrawlJob(channel_id=channel_id)
        db.add(job)
        await db.commit()
        return job.id


def _sample(n: int) -> list[RawReview]:
    return [
        RawReview(
            author_display=f"고객{i}",
            rating=(i % 5) + 1,
            body=f"본문{i}",
            visited_at=date(2026, 6, 1),
        )
        for i in range(n)
    ]


# --------------------------- 핵심: pending → done ---------------------------
async def test_pending_job_processed_to_done(tx_sessionmaker):
    _, channel_id = await _make_channel(tx_sessionmaker)
    job_id = await _add_job(tx_sessionmaker, channel_id)

    collector = FakeCollector(_sample(5))
    await run_crawl_job(job_id, lambda ch: collector, session_factory=tx_sessionmaker)

    async with tx_sessionmaker() as db:
        job = await db.get(models.CrawlJob, job_id)
        assert job.status == "done"
        assert job.collected == 5
        assert job.started_at is not None and job.finished_at is not None
        cnt = (
            await db.execute(
                select(func.count())
                .select_from(models.Review)
                .where(models.Review.channel_id == channel_id)
            )
        ).scalar_one()
        assert cnt == 5


async def test_process_pending_jobs_picks_all(tx_sessionmaker):
    _, channel_id = await _make_channel(tx_sessionmaker)
    await _add_job(tx_sessionmaker, channel_id)
    await _add_job(tx_sessionmaker, channel_id)

    processed = await process_pending_jobs(
        lambda ch: FakeCollector(_sample(3)), session_factory=tx_sessionmaker
    )
    assert processed == 2
    async with tx_sessionmaker() as db:
        remaining = (
            await db.execute(
                select(func.count())
                .select_from(models.CrawlJob)
                .where(models.CrawlJob.status == "pending")
            )
        ).scalar_one()
        assert remaining == 0


# --------------------------- 실패 & 백오프 ---------------------------
async def test_job_fails_after_exhausting_retries(tx_sessionmaker):
    _, channel_id = await _make_channel(tx_sessionmaker)
    job_id = await _add_job(tx_sessionmaker, channel_id)

    collector = FakeCollector(_sample(2), fail_times=99)  # 항상 실패
    noop_sleep = _make_noop_sleep()
    await run_crawl_job(
        job_id, lambda ch: collector, session_factory=tx_sessionmaker, sleep=noop_sleep
    )

    async with tx_sessionmaker() as db:
        job = await db.get(models.CrawlJob, job_id)
        assert job.status == "failed"
        assert job.collected == 0
        assert "셀렉터" in job.error
    assert collector.calls == 4  # 최초 1 + 재시도 3


async def test_backoff_retries_then_succeeds():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("일시 오류")
        return 7

    slept: list[float] = []

    async def fake_sleep(sec):
        slept.append(sec)

    result = await _run_with_backoff(flaky, sleep=fake_sleep)
    assert result == 7
    assert calls["n"] == 3
    assert slept == [300, 1800]  # 2번 실패 → 2번 대기


def _make_noop_sleep():
    async def _sleep(_sec):
        return None

    return _sleep


async def test_retry_recovers_after_db_error_poisons_session(tx_sessionmaker):
    """1차 시도가 DB 오류로 세션을 오염시켜도(aborted tx) 롤백 후 재시도가 성공해야 한다."""
    _, channel_id = await _make_channel(tx_sessionmaker)
    job_id = await _add_job(tx_sessionmaker, channel_id)

    class PoisonThenOk(BaseCollector):
        def __init__(self):
            self.calls = 0

        async def collect(self, channel, stop_after_known=2, known_keys=None):
            self.calls += 1
            if self.calls == 1:
                # 세션에 잘못된 SQL 을 흘려 트랜잭션을 aborted 상태로 만든 뒤 실패
                from sqlalchemy import text as sql_text

                try:
                    await self._db.execute(sql_text("select * from 없는테이블"))
                except Exception:
                    pass
                raise RuntimeError("1차 실패(세션 오염)")
            return _sample(3)

    collector = PoisonThenOk()

    def factory(ch):
        return collector

    # collector 가 세션에 접근할 수 있도록 주입 (오염 시뮬레이션용)
    async def patched_run():
        from app import worker as w

        orig = w._crawl_channel

        async def crawl_with_db(db, channel, coll):
            coll._db = db
            return await orig(db, channel, coll)

        w._crawl_channel = crawl_with_db
        try:
            await run_crawl_job(
                job_id, factory, session_factory=tx_sessionmaker, sleep=_make_noop_sleep()
            )
        finally:
            w._crawl_channel = orig

    await patched_run()

    async with tx_sessionmaker() as db:
        job = await db.get(models.CrawlJob, job_id)
        assert job.status == "done"  # 오염에도 불구하고 2차 시도 성공
        assert job.collected == 3
    assert collector.calls == 2


# --------------------------- 정기 크롤 적재 ---------------------------
async def test_enqueue_skips_channels_with_pending_job(tx_sessionmaker):
    _, ch_free = await _make_channel(tx_sessionmaker)
    _, ch_busy = await _make_channel(tx_sessionmaker)
    await _add_job(tx_sessionmaker, ch_busy)  # 이미 pending

    enqueued = await enqueue_scheduled_crawls(session_factory=tx_sessionmaker)
    assert enqueued >= 1  # (실DB에 다른 naver 채널이 있어도 견고하게)

    async with tx_sessionmaker() as db:
        cnt_busy = (
            await db.execute(
                select(func.count())
                .select_from(models.CrawlJob)
                .where(models.CrawlJob.channel_id == ch_busy)
            )
        ).scalar_one()
        cnt_free = (
            await db.execute(
                select(func.count())
                .select_from(models.CrawlJob)
                .where(models.CrawlJob.channel_id == ch_free)
            )
        ).scalar_one()
    assert cnt_busy == 1  # 중복 적재 없음
    assert cnt_free == 1


# --------------------------- 0건 2연속 자가진단 ---------------------------
def test_is_structure_change_suspected():
    assert is_structure_change_suspected(0, 0) is True
    assert is_structure_change_suspected(0, None) is False  # 첫 크롤
    assert is_structure_change_suspected(0, 3) is False
    assert is_structure_change_suspected(2, 0) is False


async def test_two_consecutive_zero_records_system_alert(tx_sessionmaker):
    store_id, channel_id = await _make_channel(tx_sessionmaker)

    empty = lambda ch: FakeCollector([])  # noqa: E731 - 매번 0건

    async def _system_alert_count() -> int:
        async with tx_sessionmaker() as db:
            return (
                await db.execute(
                    select(func.count())
                    .select_from(models.Alert)
                    .where(models.Alert.store_id == store_id, models.Alert.kind == "system")
                )
            ).scalar_one()

    # 1차 0건 → 아직 아님 (previous 없음)
    job1 = await _add_job(tx_sessionmaker, channel_id)
    await run_crawl_job(job1, empty, session_factory=tx_sessionmaker)
    assert await _system_alert_count() == 0

    # 2차 0건 → 구조 변경 의심 기록
    job2 = await _add_job(tx_sessionmaker, channel_id)
    await run_crawl_job(job2, empty, session_factory=tx_sessionmaker)
    assert await _system_alert_count() == 1


# --------------------------- /internal/crawl:trigger ---------------------------
async def test_internal_trigger_requires_key_and_inserts_job(client, db):
    # 채널 준비
    store = models.Store(owner_id=uuid4(), name="트리거")
    db.add(store)
    await db.flush()
    channel = models.StoreChannel(store_id=store.id, platform="naver")
    db.add(channel)
    await db.flush()
    await db.commit()

    from app.config import settings

    # 키 없음 → 401
    res = await client.post("/internal/crawl:trigger", json={"channel_id": channel.id})
    assert res.status_code == 401

    # 올바른 키 → pending 잡 생성
    res = await client.post(
        "/internal/crawl:trigger",
        json={"channel_id": channel.id},
        headers={"X-Internal-Key": settings.internal_api_key},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "pending"
    job_id = res.json()["job_id"]
    assert await db.get(models.CrawlJob, job_id) is not None

    # 없는 채널 → 404
    res = await client.post(
        "/internal/crawl:trigger",
        json={"channel_id": 99999999},
        headers={"X-Internal-Key": settings.internal_api_key},
    )
    assert res.status_code == 404
