"""주간 리포트 응답 DTO."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    week_start: date
    diagnosis: list  # [{level,title,evidence}]
    prescriptions: list  # [{title,detail,expected_effect}]
    created_at: datetime
