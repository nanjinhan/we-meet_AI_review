"""수집기 공통 인터페이스.

naver / google(P2) / csv 수집기가 모두 이 인터페이스를 구현한다.
RawReview.author_display 원문은 collector 밖으로 유출 금지 — 저장 시 mask_author 로
마스킹하고 원문 표시명은 저장하지 않는다 (TECH_SPEC §3.4).
(BACKEND.md §5)
"""

from abc import ABC, abstractmethod
from datetime import date
from hashlib import sha1

from pydantic import BaseModel

from app.models import StoreChannel


class RawReview(BaseModel):
    author_display: str = ""  # 저장 전 마스킹됨 — collector 밖으로 원문 유출 금지
    rating: int | None = None  # 1~5, 네이버 미제공 시 None
    body: str
    visited_at: date | None = None


class BaseCollector(ABC):
    @abstractmethod
    async def collect(
        self,
        channel: StoreChannel,
        stop_after_known: int = 2,
        known_keys: set[str] | None = None,
    ) -> list[RawReview]:
        """증분 수집. known_keys 는 이미 저장된 dedup_key 집합(중단 판정용)."""


def dedup_key(r: RawReview) -> str:
    """sha1(작성자표시명 + 방문일 + 본문 앞 50자) — TECH_SPEC §3.2 중복 키."""
    visited = r.visited_at.isoformat() if r.visited_at else ""
    raw = f"{r.author_display}|{visited}|{r.body[:50]}"
    return sha1(raw.encode("utf-8")).hexdigest()


def mask_author(name: str) -> str:
    """'김철수' -> '김**'. 첫 글자만 남기고 마스킹. 빈 문자열은 그대로."""
    name = name.strip()
    if not name:
        return ""
    if len(name) == 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)
