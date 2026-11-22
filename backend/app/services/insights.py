"""근거 진단 — 분석 결과마다 '어떤 리뷰를 근거로, 몇 건 중 몇 건, 자료가 충분한지'를 함께 내려준다.

설계 원칙:
1. **건수와 근거 목록은 같은 행에서 나온다.** 사전집계(weekly_aspect_stats)를 다시 읽지 않고, 화면에
   나열할 리뷰 자체를 세어 "N건 중 M건"을 만든다 → 요약의 모든 주장이 원문으로 뒷받침된다.
   기간 창은 대시보드와 같은 주 단위(_recent_weeks)라, 같은 기간이면 대시보드 수치와 맞는다.
2. **만족도와 자료 충분도를 분리한다.** 자료가 적으면 '적음'이라고 말한다(services/sufficiency.py).
3. **의심 신호는 검토용이다.** 같은 문장 반복을 찾아 보여주되 가짜로 단정하거나 자동 제외하지
   않는다. 부정적이라고 영향력을 낮추지도, 길고 세련된 글이라고 높이지도 않는다
   — 모든 리뷰는 1건이다.
4. 단위는 '리뷰 N건'. 작성자 표시가 마스킹돼 있어 '고객 N명'은 셀 수 없다.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Review, ReviewAnalysis, StoreChannel
from app.pipeline.stats import week_start_of
from app.schemas.insights import (
    CheckReview,
    Coverage,
    EvidenceOut,
    EvidenceReview,
    InsightItem,
    InsightsOut,
    KeywordCount,
    QuoteSample,
    ReviewCheck,
    Sufficiency,
    WeekCount,
)
from app.services.dashboard import _recent_weeks
from app.services.review_text import long_units, normalize_text
from app.services.sufficiency import (
    ISSUE_MIN_RELATED,
    SUFFICIENCY_GOOD_FROM,
    SUFFICIENCY_LOW_BELOW,
    sufficiency_level,
)

# 같은 문장 반복 검토: 정규화 글자 수가 이보다 짧은 문장은 비교하지 않는다.
# 짧은 표현("음식이 맛있고 친절해요")은 서로 다른 고객이 똑같이 쓸 수 있어 오탐이 된다.
SIMILAR_MIN_LEN = 20
MAX_CHECKS = 20  # 검토 신호는 사람이 읽을 수 있는 양만
CARD_QUOTES = 2  # 카드 미리보기 근거 문장 수
EVIDENCE_LIMIT = 100  # 근거 목록 최대 길이(넘으면 truncated=true)
OPPOSITE_LIMIT = 10
KEYWORD_LIMIT = 6
_CHECK_TEXT_MAX = 300


@dataclass
class ReviewRow:
    """기간 내 리뷰 1건 + 분석 결과. 이 모듈의 모든 건수는 이 행들을 세어 만든다."""

    id: int
    channel_id: int
    platform: str
    author_masked: str | None
    rating: int | None
    body: str
    written_at: date
    excluded: bool  # 점주가 분석에서 제외
    state: str  # analyzed / pending(분석 전) / failed
    aspects: list[dict]
    keywords: list[str]

    def mentions(self, aspect: str, polarity: str) -> bool:
        return any(
            a.get("category") == aspect and a.get("polarity") == polarity for a in self.aspects
        )

    def quote_for(self, aspect: str, polarity: str) -> str | None:
        """이 항목의 근거 문장. 저장 경로가 무엇이든 원문에 없는 인용은 내보내지 않는다."""
        for a in self.aspects:
            if a.get("category") == aspect and a.get("polarity") == polarity:
                quote = a.get("quote")
                if isinstance(quote, str) and quote and quote in self.body:
                    return quote
                return None
        return None


async def load_rows(db: AsyncSession, store_id: int, start: date, end: date) -> list[ReviewRow]:
    """[start, end) 에 작성된 내 매장(경쟁 채널 제외) 리뷰 + 분석. 최신순."""
    stmt = (
        select(Review, ReviewAnalysis, StoreChannel.platform)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .outerjoin(ReviewAnalysis, ReviewAnalysis.review_id == Review.id)
        .where(
            StoreChannel.store_id == store_id,
            StoreChannel.is_competitor.is_(False),
            Review.written_at >= start,
            Review.written_at < end,
        )
        .order_by(Review.written_at.desc(), Review.id.desc())
    )
    rows: list[ReviewRow] = []
    for review, analysis, platform in (await db.execute(stmt)).all():
        if analysis is None:
            state = "pending"
        elif analysis.model_ver == "failed":
            state = "failed"
        else:
            state = "analyzed"
        rows.append(
            ReviewRow(
                id=review.id,
                channel_id=review.channel_id,
                platform=platform,
                author_masked=review.author_masked,
                rating=review.rating,
                body=review.body,
                written_at=review.written_at,
                excluded=review.excluded_at is not None,
                state=state,
                aspects=list(analysis.aspects or []) if state == "analyzed" else [],
                keywords=list(analysis.keywords or []) if state == "analyzed" else [],
            )
        )
    return rows


def usable(rows: list[ReviewRow]) -> list[ReviewRow]:
    """분석에 쓰이는 리뷰 = 분석 완료 & 제외되지 않음. 모든 'N건 중'의 분모."""
    return [r for r in rows if r.state == "analyzed" and not r.excluded]


async def _undated_cnt(db: AsyncSession, store_id: int) -> int:
    """작성일이 없어 어떤 기간 집계에도 들어가지 못한 리뷰 수(누락 표시용)."""
    stmt = (
        select(func.count())
        .select_from(Review)
        .join(StoreChannel, StoreChannel.id == Review.channel_id)
        .where(
            StoreChannel.store_id == store_id,
            StoreChannel.is_competitor.is_(False),
            Review.written_at.is_(None),
            Review.excluded_at.is_(None),
        )
    )
    return (await db.execute(stmt)).scalar_one()


@dataclass
class _Window:
    weeks: list[date]  # 주 시작일(월요일)들
    start: date  # 포함
    end: date  # 제외
    period_end: date  # 화면 표시용 마지막 날(포함)


def _window(range_weeks: int, today: date | None, as_of: date | None) -> _Window:
    """대시보드와 같은 주 단위 창. as_of 를 주면 그 날짜가 속한 주까지(리포트 기준 주 등)."""
    today = today or datetime.now(UTC).date()
    anchor = min(as_of, today) if as_of else today
    weeks = _recent_weeks(anchor, range_weeks)
    start, end = min(weeks), max(weeks) + timedelta(weeks=1)
    period_end = min(end - timedelta(days=1), today)
    return _Window(weeks=weeks, start=start, end=end, period_end=period_end)


def _coverage(cur: list[ReviewRow], win: _Window, undated: int) -> Coverage:
    included = [r for r in cur if not r.excluded]
    return Coverage(
        period_start=win.start,
        period_end=win.period_end,
        collected_cnt=len(cur),
        analyzed_cnt=sum(1 for r in included if r.state == "analyzed"),
        pending_cnt=sum(1 for r in included if r.state == "pending"),
        failed_cnt=sum(1 for r in included if r.state == "failed"),
        excluded_cnt=len(cur) - len(included),
        undated_cnt=undated,
    )


def _keys(row: ReviewRow) -> set[tuple[str, str]]:
    """리뷰가 언급한 (항목, 방향) 집합 — 한 리뷰는 같은 조합에 한 번만 센다."""
    return {
        (a.get("category"), a.get("polarity"))
        for a in row.aspects
        if a.get("category") and a.get("polarity") in ("pos", "neg")
    }


def _other(polarity: str) -> str:
    return "pos" if polarity == "neg" else "neg"


def _items(
    cur_ok: list[ReviewRow], prev_ok: list[ReviewRow], range_weeks: int
) -> list[InsightItem]:
    by_key: dict[tuple[str, str], list[ReviewRow]] = defaultdict(list)
    for row in cur_ok:  # 최신순 유지
        for key in _keys(row):
            by_key[key].append(row)
    prev_cnt: Counter = Counter()
    for row in prev_ok:
        prev_cnt.update(_keys(row))

    items: list[InsightItem] = []
    for (aspect, polarity), related in by_key.items():
        # 미리보기는 서로 다른 문장으로 — 같은 표현(또는 중복 기록)이 두 줄을 차지하지 않게.
        # 건수에는 영향이 없다: 건수는 언제나 related 의 길이다.
        quotes: list[QuoteSample] = []
        shown: set[str] = set()
        for row in related:
            quote = row.quote_for(aspect, polarity)
            if not quote or normalize_text(quote) in shown:
                continue
            shown.add(normalize_text(quote))
            quotes.append(QuoteSample(review_id=row.id, quote=quote, written_at=row.written_at))
            if len(quotes) == CARD_QUOTES:
                break
        items.append(
            InsightItem(
                aspect=aspect,
                polarity=polarity,
                related_cnt=len(related),
                analyzed_cnt=len(cur_ok),
                opposite_cnt=len(by_key.get((aspect, _other(polarity)), [])),
                weeks_mentioned=len({week_start_of(r.written_at) for r in related}),
                range_weeks=range_weeks,
                last_written_at=max(r.written_at for r in related),
                prev_related_cnt=prev_cnt[(aspect, polarity)],
                prev_analyzed_cnt=len(prev_ok),
                enough=len(related) >= ISSUE_MIN_RELATED,
                quotes=quotes,
            )
        )
    items.sort(key=lambda i: (-i.related_cnt, i.aspect))
    return items


# --------------------------- 검토 신호: 중복 기록 / 같은 문장 ---------------------------
def _same_author(a: ReviewRow, b: ReviewRow) -> bool:
    """작성자 표시가 충돌하지 않는가. 한쪽이 비어 있으면(CSV 에 작성자 열 없음) 같다고 본다."""
    if a.author_masked is None or b.author_masked is None:
        return True
    return a.author_masked == b.author_masked


def _duplicate_clusters(rows: list[ReviewRow]) -> list[list[ReviewRow]]:
    """같은 리뷰 기록이 두 번 수집된 것으로 보이는 묶음.

    조건: 본문(정규화)과 작성일이 같고, **채널이 서로 다르며**, 작성자 표시가 충돌하지 않는다.
    같은 채널 안에서는 수집 단계의 dedup_key(작성자 원문+방문일+본문)가 같은 기록을 이미 걸러낸다.
    그래서 같은 채널에 남아 있는 '같은 문장·같은 날짜' 리뷰는 서로 다른 사람이 쓴 독립된 리뷰다
    — 묶지 않는다.
    """
    buckets: dict[tuple[str, date], list[ReviewRow]] = defaultdict(list)
    for row in rows:
        key = normalize_text(row.body)
        if key:
            buckets[(key, row.written_at)].append(row)

    clusters: list[list[ReviewRow]] = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        groups: list[list[ReviewRow]] = []
        for member in sorted(members, key=lambda r: r.id):
            for group in groups:
                if all(
                    other.channel_id != member.channel_id and _same_author(other, member)
                    for other in group
                ):
                    group.append(member)
                    break
            else:
                groups.append([member])
        clusters.extend(group for group in groups if len(group) > 1)
    return clusters


def _check_review(row: ReviewRow) -> CheckReview:
    return CheckReview(
        id=row.id,
        author_masked=row.author_masked,
        rating=row.rating,
        written_at=row.written_at,
        platform=row.platform,
        body=row.body,
    )


def find_review_checks(rows: list[ReviewRow]) -> list[ReviewCheck]:
    """사람이 확인할 검토 신호 목록. 이미 제외된 리뷰는 대상에서 뺀다(처리 완료).

    여기서 하는 일은 '찾아서 보여주기'까지다. 제외 여부는 점주가 결정한다.
    """
    rows = [r for r in rows if not r.excluded]
    clusters = _duplicate_clusters(rows)
    checks = [
        ReviewCheck(
            kind="duplicate_record",
            text=cluster[0].body.strip()[:_CHECK_TEXT_MAX],
            reviews=[_check_review(r) for r in cluster],
        )
        for cluster in sorted(clusters, key=lambda c: -max(r.id for r in c))
    ]

    # 중복 기록은 대표 1건만 남기고 문장을 비교한다(같은 기록을 '같은 문장 반복'으로 또 세지 않게).
    shadow = {r.id for cluster in clusters for r in cluster[1:]}
    by_unit: dict[str, tuple[str, list[ReviewRow]]] = {}
    for row in rows:
        if row.id in shadow:
            continue
        for key, text in long_units(row.body, SIMILAR_MIN_LEN):
            by_unit.setdefault(key, (text, []))[1].append(row)

    # 같은 리뷰 묶음이 문장만 달리해 여러 번 잡히면 가장 긴 문장 하나로 합친다.
    merged: dict[frozenset[int], tuple[str, list[ReviewRow]]] = {}
    for text, members in by_unit.values():
        if len(members) < 2:
            continue
        ids = frozenset(m.id for m in members)
        current = merged.get(ids)
        if current is None or len(text) > len(current[0]):
            merged[ids] = (text, members)
    # 더 큰 묶음에 통째로 포함되는 묶음은 뺀다(같은 신호의 반복).
    groups = [
        (text, members)
        for ids, (text, members) in merged.items()
        if not any(ids < other for other in merged)
    ]
    groups.sort(key=lambda g: (-len(g[1]), -max(m.id for m in g[1])))
    checks.extend(
        ReviewCheck(
            kind="similar_text",
            text=text[:_CHECK_TEXT_MAX],
            reviews=[_check_review(m) for m in members],
        )
        for text, members in groups
    )
    return checks[:MAX_CHECKS]


# --------------------------- 조립 ---------------------------
async def build_insights(
    db: AsyncSession,
    store_id: int,
    range_weeks: int = 4,
    today: date | None = None,
    as_of: date | None = None,
) -> InsightsOut:
    win = _window(range_weeks, today, as_of)
    prev_start = win.start - timedelta(weeks=range_weeks)
    rows = await load_rows(db, store_id, prev_start, win.end)
    cur = [r for r in rows if r.written_at >= win.start]
    cur_ok = usable(cur)
    prev_ok = usable([r for r in rows if r.written_at < win.start])

    items = _items(cur_ok, prev_ok, range_weeks)
    return InsightsOut(
        range_weeks=range_weeks,
        coverage=_coverage(cur, win, await _undated_cnt(db, store_id)),
        sufficiency=Sufficiency(
            level=sufficiency_level(len(cur_ok)),
            analyzed_cnt=len(cur_ok),
            low_below=SUFFICIENCY_LOW_BELOW,
            good_from=SUFFICIENCY_GOOD_FROM,
        ),
        issue_min_related=ISSUE_MIN_RELATED,
        issues=[i for i in items if i.polarity == "neg"],
        strengths=[i for i in items if i.polarity == "pos"],
        checks=find_review_checks(cur),
    )


def _evidence_review(row: ReviewRow, aspect: str, polarity: str) -> EvidenceReview:
    return EvidenceReview(
        id=row.id,
        author_masked=row.author_masked,
        rating=row.rating,
        written_at=row.written_at,
        platform=row.platform,
        body=row.body,
        quote=row.quote_for(aspect, polarity),
        keywords=row.keywords,
    )


async def build_evidence(
    db: AsyncSession,
    store_id: int,
    aspect: str,
    polarity: str,
    range_weeks: int = 4,
    today: date | None = None,
    as_of: date | None = None,
) -> EvidenceOut:
    """항목×방향 하나의 근거: 관련 리뷰 원문 + 근거 문장 + 반대 의견 + 주별 반복."""
    win = _window(range_weeks, today, as_of)
    cur = await load_rows(db, store_id, win.start, win.end)
    cur_ok = usable(cur)
    related = [r for r in cur_ok if r.mentions(aspect, polarity)]
    opposite = [r for r in cur_ok if r.mentions(aspect, _other(polarity))]

    weekly = [
        WeekCount(
            week_start=wk,
            related_cnt=sum(1 for r in related if week_start_of(r.written_at) == wk),
            analyzed_cnt=sum(1 for r in cur_ok if week_start_of(r.written_at) == wk),
        )
        for wk in sorted(win.weeks)
    ]
    keyword_cnt: Counter = Counter()
    for row in related:
        keyword_cnt.update(set(row.keywords))  # 한 리뷰에 같은 키워드가 두 번 있어도 1건

    return EvidenceOut(
        aspect=aspect,
        polarity=polarity,
        range_weeks=range_weeks,
        coverage=_coverage(cur, win, await _undated_cnt(db, store_id)),
        related_cnt=len(related),
        analyzed_cnt=len(cur_ok),
        opposite_cnt=len(opposite),
        enough=len(related) >= ISSUE_MIN_RELATED,
        issue_min_related=ISSUE_MIN_RELATED,
        weekly=weekly,
        keywords=[
            KeywordCount(keyword=k, count=c)
            # 동률은 가나다순 — 요청마다 순서가 흔들리지 않게
            for k, c in sorted(keyword_cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:KEYWORD_LIMIT]
        ],
        reviews=[_evidence_review(r, aspect, polarity) for r in related[:EVIDENCE_LIMIT]],
        opposite_reviews=[
            _evidence_review(r, aspect, _other(polarity)) for r in opposite[:OPPOSITE_LIMIT]
        ],
        truncated=len(related) > EVIDENCE_LIMIT,
    )
