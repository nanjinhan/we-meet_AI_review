"""collectors 단위 테스트: mask_author / dedup_key / CSV 파서. (BACKEND.md §11)"""

from datetime import date

from app.collectors.base import RawReview, dedup_key, mask_author
from app.collectors.csv_import import parse_csv


# --------------------------- mask_author ---------------------------
def test_mask_author():
    assert mask_author("김철수") == "김**"
    assert mask_author("이영") == "이*"
    assert mask_author("A") == "*"
    assert mask_author("") == ""
    assert mask_author("  김철수  ") == "김**"  # 공백 트림


# --------------------------- dedup_key ---------------------------
def test_dedup_key_stable_and_distinct():
    a = RawReview(author_display="김철수", rating=5, body="맛있어요", visited_at=date(2026, 7, 1))
    same = RawReview(
        author_display="김철수", rating=1, body="맛있어요", visited_at=date(2026, 7, 1)
    )
    other = RawReview(
        author_display="김철수", rating=5, body="별로예요", visited_at=date(2026, 7, 1)
    )

    assert dedup_key(a) == dedup_key(same)  # 별점은 키에 안 들어간다 (작성자+방문일+본문 50자)
    assert dedup_key(a) != dedup_key(other)


def test_dedup_key_uses_first_50_chars():
    long_body = "가" * 50
    a = RawReview(body=long_body + "뒤에 다른 내용 1")
    b = RawReview(body=long_body + "완전히 다른 꼬리 2")
    assert dedup_key(a) == dedup_key(b)  # 앞 50자가 같으면 같은 키


# --------------------------- parse_csv ---------------------------
def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_parse_csv_basic_with_header():
    data = _csv_bytes(
        "작성일,별점,본문,작성자\n"
        "2026-07-01,5,맛있어요,김철수\n"
        "2026.07.02,,별점 없는 리뷰\n"  # 별점 생략 허용
    )
    rows, skipped = parse_csv(data)
    assert skipped == 0
    assert len(rows) == 2
    assert rows[0].author_display == "김철수"
    assert rows[0].rating == 5
    assert rows[0].visited_at == date(2026, 7, 1)
    assert rows[1].rating is None
    assert rows[1].visited_at == date(2026, 7, 2)


def test_parse_csv_skips_bad_rows():
    data = _csv_bytes(
        "2026-07-01,5,정상 리뷰\n"
        "날짜아님,5,본문\n"  # 날짜 파싱 실패
        "2026-07-02,9,별점 범위 밖\n"  # rating 9
        "2026-07-03,4,\n"  # 본문 없음
        "\n"  # 빈 행 — 실패로 안 센다
    )
    rows, skipped = parse_csv(data)
    assert len(rows) == 1
    assert skipped == 3


def test_parse_csv_cp949():
    data = "2026-07-01,5,한국어 리뷰,박영희\n".encode("cp949")
    rows, skipped = parse_csv(data)
    assert skipped == 0
    assert rows[0].body == "한국어 리뷰"
    assert rows[0].author_display == "박영희"
