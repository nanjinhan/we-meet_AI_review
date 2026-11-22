"""리뷰 인박스 DTO (커서 페이지네이션) + 분석 제외."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator


class ReviewItem(BaseModel):
    id: int
    author_masked: str | None
    rating: int | None
    body: str
    written_at: date | None
    sentiment: str | None
    severity: str | None
    urgent: bool
    aspects: list[dict]  # [{category, polarity, quote?}] — quote 는 원문 대조를 통과한 근거 문장
    keywords: list[str]
    answered: bool
    reply_draft: str | None  # 현재 초안/승인된 답글 (인박스 표시용)
    excluded: bool = False  # 점주가 분석에서 제외한 리뷰
    exclude_reason: str | None = None


class ReviewsPage(BaseModel):
    items: list[ReviewItem]
    next_cursor: int | None  # 다음 페이지 cursor (마지막 페이지면 null)


class ExclusionIn(BaseModel):
    """리뷰를 분석에서 제외/다시 포함. 제외할 때는 이유를 반드시 남긴다(제외 내역에 표시)."""

    excluded: bool
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None

    @model_validator(mode="after")
    def _reason_required(self) -> "ExclusionIn":
        if self.excluded and not self.reason:
            raise ValueError("제외할 때는 이유를 남겨 주세요.")
        return self


class ExclusionOut(BaseModel):
    review_id: int
    excluded: bool
    exclude_reason: str | None
    excluded_at: datetime | None
