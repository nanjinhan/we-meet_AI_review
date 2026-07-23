"""T-12 완료 조건: '프롬프트에 없는 숫자' 케이스에서 재생성 분기 (LLM mock 2회 응답).

+ 클린 시 재생성 안 함, 재실패 시 항목 제거, reports 라우터.
"""

from datetime import date
from uuid import uuid4

from app import models
from app.llm.schemas import Diagnosis, Prescription, WeeklyReportOut
from app.pipeline.report_gen import generate_weekly_report
from tests.conftest import auth_headers

WK = date(2026, 6, 1)


async def _seed(db, owner) -> int:
    store = models.Store(owner_id=owner, name="리포트매장")
    db.add(store)
    await db.flush()
    # 허용 숫자: 10,6,4,60(%),4.0(avg) + 대기시간 1,3,4
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=WK, aspect="전체",
                                    pos_cnt=6, neg_cnt=4, total_cnt=10, avg_rating=4.0))
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=WK, aspect="대기시간",
                                    pos_cnt=1, neg_cnt=3, total_cnt=4, avg_rating=2.5))
    await db.flush()
    return store.id


def _presc():
    return [Prescription(title="사전주문 도입", detail="앱 주문", expected_effect="대기 감소")]


def _seq_generate(reports: list[WeeklyReportOut], counter: dict):
    it = iter(reports)

    async def fake(prompt_name, variables, output_model):
        counter["n"] += 1
        return next(it)

    return fake


# --------------------------- 재생성 분기 (완료 조건) ---------------------------
async def test_regenerates_on_unknown_number(db):
    store_id = await _seed(db, uuid4())
    counter = {"n": 0}
    gen = _seq_generate(
        [
            # 1차: 999 는 집계에 없는 숫자 → 환각 → 재생성
            WeeklyReportOut(
                diagnosis=[Diagnosis(level="crit", title="부정 급증",
                                     evidence="부정이 4건에서 999건으로 급증")],
                prescriptions=_presc(),
            ),
            # 2차: 4 는 집계에 있음 → 정상
            WeeklyReportOut(
                diagnosis=[Diagnosis(level="warn", title="부정 주의", evidence="부정 4건 확인")],
                prescriptions=_presc(),
            ),
        ],
        counter,
    )
    report = await generate_weekly_report(db, store_id, WK, generate_fn=gen)
    assert counter["n"] == 2  # 재생성 1회
    assert len(report.diagnosis) == 1
    assert report.diagnosis[0]["title"] == "부정 주의"


async def test_clean_first_no_regenerate(db):
    store_id = await _seed(db, uuid4())
    counter = {"n": 0}
    gen = _seq_generate(
        [
            WeeklyReportOut(
                diagnosis=[Diagnosis(level="strength", title="긍정 우위", evidence="긍정 6건")],
                prescriptions=_presc(),
            )
        ],
        counter,
    )
    report = await generate_weekly_report(db, store_id, WK, generate_fn=gen)
    assert counter["n"] == 1  # 재생성 없음
    assert report.diagnosis[0]["title"] == "긍정 우위"


async def test_both_bad_drops_offending_item(db):
    store_id = await _seed(db, uuid4())
    counter = {"n": 0}
    bad = WeeklyReportOut(
        diagnosis=[Diagnosis(level="crit", title="환각", evidence="부정 999건")],
        prescriptions=_presc(),
    )
    gen = _seq_generate([bad, bad], counter)
    report = await generate_weekly_report(db, store_id, WK, generate_fn=gen)
    assert counter["n"] == 2
    assert report.diagnosis == []  # 문제 항목 제거
    assert len(report.prescriptions) == 1  # 처방은 유지


# --------------------------- 라우터 ---------------------------
async def test_reports_router_latest_and_by_id(client, db):
    owner = uuid4()
    h = auth_headers(owner)
    store_id = await _seed(db, owner)

    async def gen(prompt_name, variables, output_model):
        return WeeklyReportOut(
            diagnosis=[Diagnosis(level="strength", title="좋음", evidence="긍정 6건")],
            prescriptions=_presc(),
        )

    rep = await generate_weekly_report(db, store_id, WK, generate_fn=gen)
    await db.flush()

    latest = (await client.get(f"/api/v1/stores/{store_id}/reports/latest", headers=h)).json()
    assert latest["week_start"] == WK.isoformat()
    assert latest["diagnosis"][0]["title"] == "좋음"

    byid = (await client.get(f"/api/v1/stores/{store_id}/reports/{rep.id}", headers=h)).json()
    assert byid["id"] == rep.id

    # 타 사용자 404
    other = auth_headers(uuid4())
    assert (
        await client.get(f"/api/v1/stores/{store_id}/reports/latest", headers=other)
    ).status_code == 404
    # 없는 리포트 404
    assert (
        await client.get(f"/api/v1/stores/{store_id}/reports/99999999", headers=h)
    ).status_code == 404
