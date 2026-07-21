"""stores / channels / settings / import 요청·응답 DTO."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- stores ----------
class StoreCreate(BaseModel):
    name: str = Field(min_length=1)
    category: str | None = None  # 카페/식당/미용실
    address: str | None = None


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None
    address: str | None
    created_at: datetime


# ---------- store_settings ----------
class SettingsUpdate(BaseModel):
    tone_examples: list[str] | None = None  # 기존 답글 3~5개 (few-shot 원천)
    default_tone: Literal["polite", "friendly", "apologetic"] | None = None
    notify_urgent: bool | None = None
    notify_digest: bool | None = None


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: int
    tone_examples: list[str]
    default_tone: str
    notify_urgent: bool
    notify_digest: bool


# ---------- store_channels ----------
class ChannelCreate(BaseModel):
    platform: Literal["naver", "google", "csv"]
    external_url: str | None = None
    is_competitor: bool = False
    competitor_of: int | None = None


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    platform: str
    external_url: str | None
    is_competitor: bool


# ---------- reviews:import ----------
class ImportResult(BaseModel):
    imported: int
    skipped: int
