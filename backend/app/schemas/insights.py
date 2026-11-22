"""근거 진단 응답 DTO.

모든 건수의 단위는 '리뷰'다(작성자 수가 아님 — 작성자 표시는 마스킹돼 있어 사람 수를 셀 수 없다).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.services.sufficiency import SufficiencyLevel

Polarity = Literal["pos", "neg"]


class Coverage(BaseModel):
    """분석 범위 — '몇 건 중'의 분모가 무엇이고, 무엇이 빠졌는지."""

    period_start: date
    period_end: date  # 포함(inclusive)
    collected_cnt: int  # 기간 내 수집 리뷰(작성일 기준) = analyzed+pending+failed+excluded
    analyzed_cnt: int  # 분석에 쓰인 리뷰 — 이 화면의 모든 'N건 중'의 분모
    pending_cnt: int  # 아직 분석 전
    failed_cnt: int  # 분석 실패(재분석 대상 아님)
    excluded_cnt: int  # 점주가 분석에서 제외
    undated_cnt: int  # 작성일이 없어 어떤 기간에도 들어가지 못한 리뷰(전체 기간 누적)


class Sufficiency(BaseModel):
    """자료 충분도 — 자료량 안내이지 통계적 신뢰도가 아니다."""

    level: SufficiencyLevel
    analyzed_cnt: int
    low_below: int  # 이 미만이면 low
    good_from: int  # 이 이상이면 good


class QuoteSample(BaseModel):
    review_id: int
    quote: str  # 원문 대조를 통과한 근거 문장
    written_at: date


class InsightItem(BaseModel):
    """항목×방향 하나(예: 대기시간·불만)에 대한 근거 요약."""

    aspect: str
    polarity: Polarity
    related_cnt: int  # 이 방향으로 언급한 리뷰 수 (근거 목록의 길이와 항상 같다)
    analyzed_cnt: int  # 분모
    opposite_cnt: int  # 같은 항목을 반대로 말한 리뷰 수
    weeks_mentioned: int  # 언급이 있었던 주 수 (반복 정도)
    range_weeks: int
    last_written_at: date | None  # 가장 최근 언급
    prev_related_cnt: int  # 직전 동일 기간
    prev_analyzed_cnt: int
    enough: bool  # 관련 리뷰가 '반복'을 말하기에 충분한 수인지
    quotes: list[QuoteSample]  # 카드 미리보기용 (최대 2)


class CheckReview(BaseModel):
    id: int
    author_masked: str | None
    rating: int | None
    written_at: date | None
    platform: str
    body: str


class ReviewCheck(BaseModel):
    """사람이 확인할 검토 신호. 가짜 리뷰 판정이 아니다.

    - duplicate_record: 같은 리뷰 기록이 서로 다른 채널(예: CSV·네이버)로 두 번 들어온 것으로 보임
    - similar_text: 서로 다른 작성 기록에 같은 문장이 있음(각자 비슷한 경험을 쓴 것일 수 있음)
    """

    kind: Literal["duplicate_record", "similar_text"]
    text: str  # 반복된 문장(원문)
    reviews: list[CheckReview]


class InsightsOut(BaseModel):
    range_weeks: int
    coverage: Coverage
    sufficiency: Sufficiency
    issue_min_related: int  # InsightItem.enough 의 기준값
    issues: list[InsightItem]  # 불만 언급 — 관련 리뷰 많은 순
    strengths: list[InsightItem]  # 호평 언급 — 관련 리뷰 많은 순
    checks: list[ReviewCheck]


class EvidenceReview(BaseModel):
    id: int
    author_masked: str | None
    rating: int | None
    written_at: date | None
    platform: str
    body: str
    quote: str | None  # 이 항목의 근거 문장(본문의 연속된 구간). 없으면 본문 전체가 근거
    keywords: list[str]


class WeekCount(BaseModel):
    week_start: date
    related_cnt: int
    analyzed_cnt: int


class KeywordCount(BaseModel):
    keyword: str
    count: int  # 이 키워드가 붙은 관련 리뷰 수


class EvidenceOut(BaseModel):
    aspect: str
    polarity: Polarity
    range_weeks: int
    coverage: Coverage
    related_cnt: int
    analyzed_cnt: int
    opposite_cnt: int
    enough: bool
    issue_min_related: int
    weekly: list[WeekCount]  # 오래된→최신
    keywords: list[KeywordCount]  # 관련 리뷰에 함께 붙은 키워드
    # 관련 리뷰(최신순). truncated 가 아니면 길이가 related_cnt 와 같다
    reviews: list[EvidenceReview]
    opposite_reviews: list[EvidenceReview]  # 같은 항목을 반대로 말한 리뷰(최신순, 일부)
    truncated: bool  # 관련 리뷰가 많아 최근 것만 내려준 경우
