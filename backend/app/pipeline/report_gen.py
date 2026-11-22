"""주간 진단 리포트 생성 + 환각 수치 검증.

4주치 통계 + 급증 키워드 + 경쟁 통계를 프롬프트에 넣어 generate("report_v2", WeeklyReportOut).
**수치 검증**: diagnosis.evidence 안의 숫자가 프롬프트에 넣은 집계값 집합에 없으면 1회 재생성,
재실패 시 해당 항목 제거 후 reports UPSERT.
**근거 연결 검증**: diagnosis.aspect/polarity 는 리포트 카드에서 근거 리뷰를 여는 데 쓴다 —
집계에 실제로 있는 항목명이 아니면 지운다(없는 항목으로 가는 링크를 만들지 않는다).
(BACKEND.md §6, ARCHITECTURE.md §4, TECH_SPEC §5.3)
"""

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.schemas import WeeklyReportOut
from app.models import Report, StoreChannel, WeeklyAspectStats
from app.pipeline.stats import OVERALL
from app.services.dashboard import _aspects, _keywords, _overall_rows

logger = logging.getLogger("pipeline.report_gen")

GenerateFn = Callable[..., Awaitable[WeeklyReportOut]]
_NUM = re.compile(r"\d+(?:\.\d+)?")


async def _default_generate(
    prompt_name: str, variables: dict, output_model: type
) -> WeeklyReportOut:
    from app.llm.client import generate  # 지연 import (생성 모델 기본값)

    return await generate(prompt_name, variables, output_model)


def _extract_numbers(text: str) -> set[float]:
    return {round(float(m), 2) for m in _NUM.findall(text)}


async def _competitor_summary(db, store_id, weeks) -> tuple[str | None, set[float]]:
    comp_ids = list(
        (
            await db.execute(
                select(StoreChannel.store_id)
                .where(StoreChannel.competitor_of == store_id)
                .distinct()
            )
        ).scalars()
    )
    if not comp_ids:
        return None, set()
    pos, total = (
        await db.execute(
            select(
                func.sum(WeeklyAspectStats.pos_cnt),
                func.sum(WeeklyAspectStats.total_cnt),
            ).where(
                WeeklyAspectStats.store_id.in_(comp_ids),
                WeeklyAspectStats.week_start.in_(weeks),
                WeeklyAspectStats.aspect == OVERALL,
            )
        )
    ).one()
    if not total:
        return None, set()
    ratio = round(100 * (pos or 0) / total)
    return f"## 경쟁매장 평균 긍정비율 {ratio}%", {float(ratio)}


async def _build_context(db, store_id, week_start: date) -> tuple[str, set[float], set[str]]:
    """프롬프트용 집계 문자열 + 허용 숫자 집합 + 집계에 있는 항목명 집합.

    evidence 는 허용 숫자만 인용할 수 있고, aspect 는 항목명 집합 안의 이름만 가리킬 수 있다.
    """
    weeks = [week_start - timedelta(weeks=i) for i in range(4)]
    allowed: set[float] = set()
    lines: list[str] = ["## 주간 종합 (최근 4주, 오래된→최신)"]

    overall = {r.week_start: r for r in await _overall_rows(db, store_id, weeks)}
    for wk in sorted(weeks):
        r = overall.get(wk)
        total = r.total_cnt if r else 0
        pos = r.pos_cnt if r else 0
        neg = r.neg_cnt if r else 0
        ratio = round(100 * pos / total) if total else 0
        line = f"- {wk}: 리뷰 {total}건 · 긍정 {pos} · 부정 {neg} · 긍정비율 {ratio}%"
        for v in (total, pos, neg, ratio):
            allowed.add(float(v))
        if r and r.avg_rating:
            avg = round(float(r.avg_rating), 2)
            line += f" · 평균별점 {avg}"
            allowed.add(avg)
        lines.append(line)

    bars = await _aspects(db, store_id, weeks)
    if bars:
        lines.append("## 항목별 (4주 합계)")
        for b in bars:
            lines.append(f"- {b.aspect}: 긍정 {b.pos_cnt} · 부정 {b.neg_cnt} · 총 {b.total_cnt}")
            for v in (b.pos_cnt, b.neg_cnt, b.total_cnt):
                allowed.add(float(v))

    kws = await _keywords(db, store_id, weeks)
    if kws:
        lines.append("## 급증 키워드: " + ", ".join(kws))

    comp_line, comp_nums = await _competitor_summary(db, store_id, weeks)
    if comp_line:
        lines.append(comp_line)
        allowed |= comp_nums

    return "\n".join(lines), allowed, {b.aspect for b in bars}


def _verify(report: WeeklyReportOut, allowed: set[float]) -> tuple[bool, WeeklyReportOut]:
    """(전부 정상 여부, 문제 항목 제거된 리포트). evidence 숫자가 allowed 부분집합이어야 정상."""
    clean_diag = []
    all_clean = True
    for d in report.diagnosis:
        if _extract_numbers(d.evidence) <= allowed:
            clean_diag.append(d)
        else:
            all_clean = False
            logger.warning("리포트 환각 수치 감지 — 항목 제거 후보: %s", d.title)
    return all_clean, WeeklyReportOut(diagnosis=clean_diag, prescriptions=report.prescriptions)


def _clean_links(report: WeeklyReportOut, aspects: set[str]) -> WeeklyReportOut:
    """근거 연결 정보 정리 — 집계에 없는 항목명이거나 방향이 빠졌으면 aspect/polarity 를 지운다.

    진단 자체는 남긴다(수치 검증은 _verify 가 따로 한다) — 링크만 없어질 뿐이다.
    """
    diagnosis = []
    for d in report.diagnosis:
        aspect = (d.aspect or "").strip()
        if aspect in aspects and d.polarity is not None:
            diagnosis.append(d.model_copy(update={"aspect": aspect}))
        else:
            diagnosis.append(d.model_copy(update={"aspect": None, "polarity": None}))
    return WeeklyReportOut(diagnosis=diagnosis, prescriptions=report.prescriptions)


async def _upsert_report(db, store_id, week_start, report: WeeklyReportOut) -> Report:
    diag = [d.model_dump(exclude_none=True) for d in report.diagnosis]  # 링크 없는 진단은 키 생략
    presc = [p.model_dump() for p in report.prescriptions]
    ins = (
        pg_insert(Report)
        .values(store_id=store_id, week_start=week_start, diagnosis=diag, prescriptions=presc)
        .on_conflict_do_update(
            index_elements=["store_id", "week_start"],
            set_={"diagnosis": diag, "prescriptions": presc},
        )
        .returning(Report.id)
    )
    rid = (await db.execute(ins)).scalar_one()
    await db.flush()
    return await db.get(Report, rid)


async def generate_weekly_report(
    db: AsyncSession,
    store_id: int,
    week_start: date,
    *,
    generate_fn: GenerateFn = _default_generate,
) -> Report:
    """주간 리포트 생성 → 수치 검증(필요시 1회 재생성) → reports UPSERT. (커밋은 호출자)"""
    context, allowed, aspects = await _build_context(db, store_id, week_start)
    report = await generate_fn("report_v2", {"figures": context}, WeeklyReportOut)
    clean, filtered = _verify(report, allowed)
    if not clean:
        # 환각 수치 → 1회 재생성. 재생성 결과에서도 문제 항목은 제거한다.
        regen = await generate_fn("report_v2", {"figures": context}, WeeklyReportOut)
        _, filtered = _verify(regen, allowed)
    return await _upsert_report(db, store_id, week_start, _clean_links(filtered, aspects))
