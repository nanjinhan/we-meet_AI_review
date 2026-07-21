"""리뷰 인박스 DTO (커서 페이지네이션)."""

from datetime import date

from pydantic import BaseModel


class ReviewItem(BaseModel):
    id: int
    author_masked: str | None
    rating: int | None
    body: str
    written_at: date | None
    sentiment: str | None
    severity: str | None
    urgent: bool
    aspects: list[dict]
    keywords: list[str]
    answered: bool
    reply_draft: str | None  # 현재 초안/승인된 답글 (인박스 표시용)


class ReviewsPage(BaseModel):
    items: list[ReviewItem]
    next_cursor: int | None  # 다음 페이지 cursor (마지막 페이지면 null)
