"""CSV 업로드 폴백 파서.

포맷: `작성일,별점,본문[,작성자]` — 3컬럼 필수 + 선택 작성자 (BACKEND.md §5).
파싱 실패 행은 건너뛰고 개수만 센다. 크롤러 전면 장애 시에도 서비스가 동작함을
보장하는 P0 폴백 경로 (TECH_SPEC §3.1).
"""

import csv
import io
from datetime import date, datetime

from app.collectors.base import RawReview

_DATE_FORMATS = ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d")


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"날짜 형식 인식 불가: {value!r}")


def _decode(data: bytes) -> str:
    # 한국어 엑셀 저장본(cp949) 대비. BOM 은 utf-8-sig 로 흡수.
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp949")


def parse_csv(data: bytes) -> tuple[list[RawReview], int]:
    """CSV 바이트 → (RawReview 목록, 파싱 실패 행 수).

    헤더 행('작성일,...')은 있으면 조용히 무시한다(실패 행으로 세지 않음).
    """
    rows = list(csv.reader(io.StringIO(_decode(data))))

    # 헤더 감지: 첫 행 첫 칸이 '작성일' 류면 스킵
    if rows and rows[0] and rows[0][0].strip() in ("작성일", "written_at", "date"):
        rows = rows[1:]

    reviews: list[RawReview] = []
    skipped = 0
    for row in rows:
        if not row or all(not c.strip() for c in row):
            continue  # 완전 빈 행은 실패로 치지 않는다
        try:
            written_at = _parse_date(row[0])
            rating_str = row[1].strip() if len(row) > 1 else ""
            rating = int(rating_str) if rating_str else None
            if rating is not None and not 1 <= rating <= 5:
                raise ValueError(f"별점 범위 밖: {rating}")
            body = row[2].strip() if len(row) > 2 else ""
            if not body:
                raise ValueError("본문 없음")
            author = row[3].strip() if len(row) > 3 else ""
            reviews.append(
                RawReview(
                    author_display=author,
                    rating=rating,
                    body=body,
                    visited_at=written_at,
                )
            )
        except (ValueError, IndexError):
            skipped += 1
    return reviews, skipped
