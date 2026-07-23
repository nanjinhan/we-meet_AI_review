"""경쟁매장 비교 응답 DTO."""

from pydantic import BaseModel


class CompareAspect(BaseModel):
    aspect: str
    ours_pos: int
    ours_neg: int
    ours_total: int
    comp_pos: int
    comp_neg: int
    comp_total: int


class CompareOut(BaseModel):
    range_weeks: int
    has_competitors: bool
    aspects: list[CompareAspect]
    insight: str
