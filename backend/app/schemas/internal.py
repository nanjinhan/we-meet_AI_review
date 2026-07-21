"""내부 엔드포인트 DTO."""

from pydantic import BaseModel


class CrawlTrigger(BaseModel):
    channel_id: int


class CrawlTriggerResult(BaseModel):
    job_id: int
    status: str
