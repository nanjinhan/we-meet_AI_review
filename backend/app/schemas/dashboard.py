"""대시보드 응답 DTO."""

from datetime import date

from pydantic import BaseModel


class WeeklyPoint(BaseModel):
    week_start: date
    total_cnt: int
    pos_cnt: int
    neg_cnt: int
    avg_rating: float | None


class AspectBar(BaseModel):
    aspect: str
    pos_cnt: int
    neg_cnt: int
    total_cnt: int


class DashboardOut(BaseModel):
    range_weeks: int
    score: float
    score_delta: float | None  # 직전 동일기간 대비
    total_reviews: int
    positive_ratio: float
    avg_rating: float | None
    answer_rate: float
    trend: list[WeeklyPoint]  # 주별 추이 (오래된→최신)
    aspects: list[AspectBar]  # aspect별 긍/부정 (전체 제외)
    keywords: list[str]  # 급증 키워드
