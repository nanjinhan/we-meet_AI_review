"""LLM 출력 Pydantic 모델 (전부 여기에). 프로바이더와 무관 — 스키마 강제의 원천.

CLAUDE.md 규칙 4: LLM 출력은 전부 Pydantic 으로 스키마 강제. 자유 텍스트 파싱 금지.
(BACKEND.md §4)
"""

from typing import Literal

from pydantic import BaseModel


class AspectItem(BaseModel):
    category: Literal["맛", "친절", "청결", "대기시간", "가격", "분위기", "기타"]
    polarity: Literal["pos", "neg"]
    # 그렇게 판단한 근거 문장 — 리뷰 본문을 글자 그대로 발췌(classify_v2).
    # 서버가 원문과 대조해 통과한 것만 저장한다(pipeline/analyze.py). 없으면 null.
    quote: str | None = None


class ReviewAnalysisOut(BaseModel):
    review_index: int  # 배치 내 인덱스로 매핑
    sentiment: Literal["pos", "neu", "neg"]
    severity: Literal["normal", "uncomfortable", "complaint", "malicious"]
    urgent: bool  # 위생/이물/환불/법적 언급
    aspects: list[AspectItem]
    keywords: list[str]


class BatchAnalysisOut(BaseModel):
    results: list[ReviewAnalysisOut]


class ReplyOut(BaseModel):
    draft: str  # 150자 내외


class RouterDecision(BaseModel):
    intent: Literal["stats", "evidence", "both", "chitchat"]
    aspect: str | None = None
    sentiment: Literal["pos", "neg"] | None = None
    period_weeks: int = 4  # 최근 N주
    query_text: str | None = None  # evidence용 검색 문장


class Diagnosis(BaseModel):
    level: Literal["crit", "warn", "strength", "opportunity"]
    title: str
    evidence: str  # 반드시 프롬프트에 준 수치만 인용
    # 이 진단이 가리키는 항목과 방향(report_v2). 리포트 카드 → 근거 리뷰 연결용.
    # 서버가 집계에 실제로 있는 항목명인지 검증하고, 아니면 둘 다 null 로 지운다.
    aspect: str | None = None
    polarity: Literal["pos", "neg"] | None = None


class Prescription(BaseModel):
    title: str
    detail: str
    expected_effect: str


class WeeklyReportOut(BaseModel):
    diagnosis: list[Diagnosis]
    prescriptions: list[Prescription]
