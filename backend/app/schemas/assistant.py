"""AI 비서 DTO."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssistantIn(BaseModel):
    message: str = Field(min_length=1)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str | None
    content: str
    created_at: datetime
