"""답글 생성/승인 DTO."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Tone = Literal["polite", "friendly", "apologetic"]


class ReplyGenerateIn(BaseModel):
    tone: Tone


class ReplyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_id: int
    tone: str | None
    draft: str
    status: str
    created_at: datetime
    approved_at: datetime | None
