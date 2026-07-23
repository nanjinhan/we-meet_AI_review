"""크롤러 워커 (별도 프로세스, `python -m app.worker`).

api 와 같은 DB 를 쓰지만 FastAPI 앱은 import 하지 않는다 — collectors/services/pipeline 만.
api ↔ worker 통신 채널은 crawl_jobs 테이블 하나뿐 (HTTP/큐 없음, ARCHITECTURE §1).

스케줄 잡 5종 (BACKEND.md §8):
  1) 매장별 크롤: 09:00 / 21:00 + jitter → naver 채널마다 crawl_jobs pending 적재
  2) crawl_jobs 폴링: 10초 간격, pending → running → 수집 → done/failed
  3) 알림 다이제스트: 매시 정각 (T-10 에서 발송 연결)
  4) 주간 리포트: 월 07:00 (T-12 에서 연결)
  5) 스냅샷 청소: 일 1회, 7일 지난 HTML 삭제

핵심 로직(run_crawl_job/백오프/자가진단)은 스케줄러와 분리해 통합 테스트가 가능하도록 했다.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import BaseCollector
from app.collectors.naver import NaverCollector, rotate_all_snapshots
from app.db import SessionLocal
from app.models import Alert, CrawlJob, Review, StoreChannel
from app.services.ingest import store_raw_reviews

logger = logging.getLogger("worker")

# 크롤 실패 시 백오프(초): 5분 → 30분 → 2시간, 3회 재시도 후 포기 (BACKEND.md §8)
BACKOFF_DELAYS: tuple[int, ...] = (300, 1800, 7200)

CollectorFactory = Callable[[StoreChannel], BaseCollector]


def _now() -> datetime:
    return datetime.now(UTC)


def default_collector_factory(channel: StoreChannel) -> BaseCollector:
    if channel.platform == "naver":
        return NaverCollector()
    raise ValueError(f"크롤 미지원 플랫폼: {channel.platform}")


async def _run_with_backoff(
    fn: Callable[[], Awaitable[int]],
    *,
    delays: tuple[int, ...] = BACKOFF_DELAYS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """fn 실행. 실패하면 delays 간격으로 재시도하고, 모두 실패하면 마지막 예외를 던진다."""
    last_exc: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - 재시도 목적상 광범위 캐치
            last_exc = exc
            if attempt < len(delays):
                logger.warning("크롤 실패(재시도 %d): %s", attempt + 1, exc)
                await sleep(delays[attempt])
    assert last_exc is not None
    raise last_exc


async def _known_keys(db: AsyncSession, channel_id: int) -> set[str]:
    rows = await db.execute(
        select(Review.dedup_key).where(Review.channel_id == channel_id)
    )
    return set(rows.scalars())


async def _crawl_channel(
    db: AsyncSession, channel: StoreChannel, collector: BaseCollector
) -> int:
    """수집 → 저장. 신규 저장 건수 반환. (커밋은 호출자)"""
    known = await _known_keys(db, channel.id)
    raws = await collector.collect(channel, known_keys=known)
    return await store_raw_reviews(db, channel.id, raws)


def is_structure_change_suspected(current: int, previous: int | None) -> bool:
    """0건 2연속이면 구조 변경 의심 (TECH_SPEC §3.3). previous=None 이면 첫 크롤이라 아님."""
    return current == 0 and previous == 0


async def _previous_collected(
    db: AsyncSession, channel_id: int, exclude_job_id: int
) -> int | None:
    """직전에 끝난 크롤 잡의 수집 건수 (자가진단용)."""
    stmt = (
        select(CrawlJob.collected)
        .where(
            CrawlJob.channel_id == channel_id,
            CrawlJob.id != exclude_job_id,
            CrawlJob.finished_at.is_not(None),
        )
        .order_by(CrawlJob.finished_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def _record_self_diagnosis(
    db: AsyncSession, channel: StoreChannel, collected: int, job_id: int
) -> None:
    """0건 2연속이면 alerts 에 system 기록 (발송은 T-10). sent_via 는 비워둔다."""
    previous = await _previous_collected(db, channel.id, job_id)
    if is_structure_change_suspected(collected, previous):
        logger.warning("구조 변경 의심(0건 2연속): channel_id=%s", channel.id)
        db.add(Alert(store_id=channel.store_id, kind="system", sent_via=[]))


async def run_crawl_job(
    job_id: int,
    collector_factory: CollectorFactory = default_collector_factory,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """pending crawl_job 하나를 running → done/failed 로 처리."""
    async with session_factory() as db:
        job = await db.get(CrawlJob, job_id)
        if job is None or job.status != "pending":
            return  # 이미 다른 워커/이전 실행이 집어감
        job.status = "running"
        job.started_at = _now()
        await db.commit()

        channel_id = job.channel_id

        async def _attempt() -> int:
            # 재시도마다 channel 재조회 — 직전 실패의 rollback 이 세션 객체를 전부
            # expire 시키므로, 만료된 인스턴스를 재사용하면 MissingGreenlet 이 난다.
            ch = await db.get(StoreChannel, channel_id)
            try:
                return await _crawl_channel(db, ch, collector_factory(ch))
            except Exception:
                # 실패한 시도가 세션을 오염시키면(aborted tx) 이후 재시도가 전부 즉사한다
                # → 시도 단위로 롤백해 재시도 가능한 상태로 복구.
                await db.rollback()
                raise

        try:
            collected = await _run_with_backoff(_attempt, sleep=sleep)
            job = await db.get(CrawlJob, job_id)  # 중간 실패의 rollback 대비 재조회
            job.status = "done"
            job.collected = collected
        except Exception as exc:  # noqa: BLE001 - 실패도 기록하고 계속
            await db.rollback()
            job = await db.get(CrawlJob, job_id)
            job.status = "failed"
            job.error = str(exc)[:1000]
            job.collected = 0
            collected = 0
            logger.exception("크롤 잡 실패: job_id=%s", job_id)

        channel = await db.get(StoreChannel, channel_id)
        job.finished_at = _now()
        await _record_self_diagnosis(db, channel, collected, job_id)
        await db.commit()

        # 수집 완료 후 분석 파이프라인 자동 호출 (ARCHITECTURE §4). 분석 실패가
        # 크롤 잡 결과를 뒤엎지 않도록 별도 커밋 + best-effort.
        if job.status == "done" and collected:
            try:
                from app.pipeline.analyze import analyze_new_reviews

                await analyze_new_reviews(db, channel_id)
                await db.commit()
            except Exception as exc:  # noqa: BLE001 - 분석 실패는 크롤을 막지 않는다
                await db.rollback()
                logger.warning("수집 후 분석 실패(channel=%s): %s", channel_id, exc)


async def process_pending_jobs(
    collector_factory: CollectorFactory = default_collector_factory,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> int:
    """pending crawl_jobs 를 순차 처리. 처리한 잡 수 반환. (10초 폴링 잡)"""
    async with session_factory() as db:
        ids = list(
            (
                await db.execute(
                    select(CrawlJob.id)
                    .where(CrawlJob.status == "pending")
                    .order_by(CrawlJob.id)
                )
            ).scalars()
        )
    for job_id in ids:  # 병렬 금지 — 순차 처리
        await run_crawl_job(job_id, collector_factory, session_factory=session_factory)
    return len(ids)


async def enqueue_scheduled_crawls(
    *, session_factory: async_sessionmaker[AsyncSession] = SessionLocal
) -> int:
    """모든 naver 채널에 대해 crawl_jobs pending 적재 (정기 크롤 트리거). 적재 수 반환.

    이미 pending 잡이 있는 채널은 건너뛴다 — 워커가 밀려 있을 때(백오프 대기 등)
    같은 채널 잡이 무한 누적되는 것을 방지.
    """
    async with session_factory() as db:
        pending_sq = select(CrawlJob.channel_id).where(CrawlJob.status == "pending")
        channels = list(
            (
                await db.execute(
                    select(StoreChannel.id).where(
                        StoreChannel.platform == "naver",
                        StoreChannel.id.not_in(pending_sq),
                    )
                )
            ).scalars()
        )
        for channel_id in channels:
            db.add(CrawlJob(channel_id=channel_id, requested_by=None))
        await db.commit()
    return len(channels)


async def cleanup_snapshots() -> int:
    """7일 지난 HTML 스냅샷 삭제 (일 1회). 파일시스템 기준이라 삭제된 채널의
    고아 디렉토리도 함께 청소된다. 삭제한 파일 수 반환."""
    return rotate_all_snapshots()


# --------------------------- 미연결 잡 (스텁) ---------------------------
async def send_hourly_digest(
    *, session_factory: async_sessionmaker[AsyncSession] = SessionLocal
) -> int:
    """미발송 일반 부정 리뷰를 매장별로 묶어 다이제스트 발송. 발송 매장 수 반환."""
    from app.notify.dispatch import run_digest

    async with session_factory() as db:
        count = await run_digest(db)
        await db.commit()
    return count


async def generate_weekly_reports(
    *, session_factory: async_sessionmaker[AsyncSession] = SessionLocal
) -> int:
    """전 매장의 직전 완료 주 리포트 생성 + 완료 알림. 생성한 매장 수 반환."""
    from datetime import timedelta

    from app.models import Store
    from app.notify.dispatch import send_report_ready
    from app.pipeline.report_gen import generate_weekly_report
    from app.pipeline.stats import week_start_of

    week_start = week_start_of(_now().date()) - timedelta(weeks=1)  # 지난주 월요일
    done = 0
    async with session_factory() as db:
        store_ids = list((await db.execute(select(Store.id))).scalars())
        for sid in store_ids:
            try:
                await generate_weekly_report(db, sid, week_start)
                await send_report_ready(db, sid)
                await db.commit()
                done += 1
            except Exception as exc:  # noqa: BLE001 - 한 매장 실패가 전체를 막지 않는다
                await db.rollback()
                logger.warning("주간 리포트 실패(store=%s): %s", sid, exc)
    return done


# --------------------------- 스케줄러 ---------------------------
def build_scheduler():
    """APScheduler 구성. 엔트리포인트에서만 호출 (테스트는 위 잡 함수를 직접 검증)."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    # 1) 매장별 크롤: 09:00 / 21:00 + jitter(0~30분). 채널 순차는 폴링 잡이 보장.
    scheduler.add_job(
        enqueue_scheduled_crawls, CronTrigger(hour="9,21"), jitter=1800, id="scheduled_crawl"
    )
    # 2) crawl_jobs 폴링: 10초
    scheduler.add_job(
        process_pending_jobs, IntervalTrigger(seconds=10), id="poll_jobs", max_instances=1
    )
    # 3) 알림 다이제스트: 매시 정각
    scheduler.add_job(send_hourly_digest, CronTrigger(minute=0), id="digest")
    # 4) 주간 리포트: 월 07:00
    scheduler.add_job(
        generate_weekly_reports, CronTrigger(day_of_week="mon", hour=7), id="weekly_report"
    )
    # 5) 스냅샷 청소: 매일 04:00
    scheduler.add_job(cleanup_snapshots, CronTrigger(hour=4), id="cleanup_snapshots")
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("worker 시작 — crawl_jobs 10초 폴링")
    try:
        await asyncio.Event().wait()  # 영구 대기
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
