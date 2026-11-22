"""실행 과제 요청·응답 DTO."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

ActionStatus = Literal["active", "done", "dropped"]

_Aspect = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
_Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
_Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ActionCreate(BaseModel):
    aspect: _Aspect  # 대상 항목 (맛/친절/청결/대기시간/가격/분위기/기타)
    polarity: Literal["pos", "neg"] = "neg"
    title: _Title  # 실행할 행동
    note: _Note | None = None
    started_on: date  # 실행일


class ActionUpdate(BaseModel):
    """보낸 필드만 바꾼다. note 는 null 을 보내면 지워진다."""

    title: _Title | None = None
    note: _Note | None = None
    started_on: date | None = None
    status: ActionStatus | None = None


class ActionObservation(BaseModel):
    """실행일 전후로 같은 항목이 리뷰에 어떻게 나타났는지 — 관측일 뿐 효과 판정이 아니다.

    리뷰가 줄거나 늘어도 다른 요인(계절·행사·리뷰 수 변화)이 있을 수 있으므로,
    서버는 '개선됨' 같은 결론을 계산하지 않고 건수만 내려준다.
    """

    before_days: int  # 실행 전 비교 창 길이(일)
    before_related_cnt: int
    before_analyzed_cnt: int
    after_days: int  # 실행일 포함 경과일. 아직 실행 전이면 0
    after_related_cnt: int
    after_analyzed_cnt: int
    enough: bool  # 실행 후 분석 리뷰가 관측하기에 충분히 쌓였는지
    min_analyzed: int  # enough 의 기준값


class ActionOut(BaseModel):
    id: int
    store_id: int
    aspect: str
    polarity: str
    title: str
    note: str | None
    started_on: date
    status: str
    created_at: datetime
    observation: ActionObservation
