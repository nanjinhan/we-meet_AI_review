"""실행 과제 — 근거를 본 뒤 점주가 고른 행동과, 그 뒤 리뷰에서의 관측.

흐름: 반복 문제 후보 확인 → 원문·건수로 실제 상황과 맞는지 판단 → 이번 주 실행할 행동 하나 선택
→ 실행일·내용 기록 → 이후 리뷰에서 같은 항목이 어떻게 나타나는지 관측.

관측값은 저장하지 않고 조회할 때마다 리뷰에서 다시 센다(근거 진단과 같은 행·같은 규칙 —
services/insights.load_rows/usable). 나중에 들어온 과거 리뷰나 제외 처리도 그대로 반영된다.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionItem
from app.schemas.actions import ActionObservation, ActionOut
from app.services.insights import ReviewRow, load_rows, usable
from app.services.sufficiency import OBSERVATION_MIN_ANALYZED

BEFORE_DAYS = 28  # 실행 전 비교 창: 실행일 직전 4주


def _today() -> date:
    return datetime.now(UTC).date()


def observe(action: ActionItem, rows: list[ReviewRow], today: date) -> ActionObservation:
    """rows(분석에 쓰이는 리뷰)에서 실행일 전/후의 관련 건수를 센다."""
    before_start = action.started_on - timedelta(days=BEFORE_DAYS)
    before = [r for r in rows if before_start <= r.written_at < action.started_on]
    after = [r for r in rows if action.started_on <= r.written_at <= today]
    return ActionObservation(
        before_days=BEFORE_DAYS,
        before_related_cnt=sum(1 for r in before if r.mentions(action.aspect, action.polarity)),
        before_analyzed_cnt=len(before),
        after_days=max(0, (today - action.started_on).days + 1),
        after_related_cnt=sum(1 for r in after if r.mentions(action.aspect, action.polarity)),
        after_analyzed_cnt=len(after),
        enough=len(after) >= OBSERVATION_MIN_ANALYZED,
        min_analyzed=OBSERVATION_MIN_ANALYZED,
    )


def _out(action: ActionItem, observation: ActionObservation) -> ActionOut:
    return ActionOut(
        id=action.id,
        store_id=action.store_id,
        aspect=action.aspect,
        polarity=action.polarity,
        title=action.title,
        note=action.note,
        started_on=action.started_on,
        status=action.status,
        created_at=action.created_at,
        observation=observation,
    )


async def _rows_for(
    db: AsyncSession, store_id: int, actions: list[ActionItem], today: date
) -> list[ReviewRow]:
    start = min(a.started_on for a in actions) - timedelta(days=BEFORE_DAYS)
    return usable(await load_rows(db, store_id, start, today + timedelta(days=1)))


async def list_actions(
    db: AsyncSession, store_id: int, today: date | None = None
) -> list[ActionOut]:
    """매장의 실행 과제 + 관측. 진행 중인 것 먼저, 그 안에서는 최근 실행일 순."""
    today = today or _today()
    stmt = (
        select(ActionItem)
        .where(ActionItem.store_id == store_id)
        .order_by(
            case((ActionItem.status == "active", 0), else_=1),
            ActionItem.started_on.desc(),
            ActionItem.id.desc(),
        )
    )
    actions = list((await db.execute(stmt)).scalars())
    if not actions:
        return []
    rows = await _rows_for(db, store_id, actions, today)
    return [_out(a, observe(a, rows, today)) for a in actions]


async def action_out(db: AsyncSession, action: ActionItem, today: date | None = None) -> ActionOut:
    """과제 1건 + 관측 (생성·수정 응답용)."""
    today = today or _today()
    rows = await _rows_for(db, action.store_id, [action], today)
    return _out(action, observe(action, rows, today))
