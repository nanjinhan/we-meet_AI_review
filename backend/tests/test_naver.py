"""T-05 완료 조건: 저장된 HTML 픽스처에서 파싱 테스트 + 증분 중단 로직 단위 테스트.

라이브 크롤(Playwright)은 테스트하지 않는다 (BACKEND.md §11). 파싱·증분·스냅샷 순수 로직만.
"""

import os
from datetime import date, datetime, timedelta

from app.collectors.base import RawReview, dedup_key
from app.collectors.naver import (
    IncrementalStopTracker,
    parse_reviews,
    rotate_all_snapshots,
    rotate_snapshots,
    save_snapshot,
)

# 합성 픽스처: 실제 네이버 셀렉터 값은 사람이 채우므로, 테스트는 자체 구조+셀렉터를 통제한다.
_SEL = {
    "review_item": ".review",
    "author": ".name",
    "body": ".text",
    "rating": ".star",
    "visited_at": ".date",
    "more_button": ".more",
}

_FIXTURE_HTML = """
<html><body>
  <div class="review">
    <span class="name">김철수</span>
    <span class="star">별점 5점</span>
    <p class="text">정말 맛있어요 재방문 의사 있습니다</p>
    <time class="date">2026.7.1</time>
  </div>
  <div class="review">
    <span class="name">이영희</span>
    <span class="star">2점</span>
    <p class="text">대기시간이 너무 길었어요</p>
    <time class="date">2026-06-28</time>
  </div>
  <div class="review">
    <span class="name">박</span>
    <p class="text">별점/날짜 없는 리뷰</p>
  </div>
  <div class="review">
    <span class="name">빈리뷰</span>
    <p class="text"></p>
  </div>
</body></html>
"""


# --------------------------- parse_reviews ---------------------------
def test_parse_fixture():
    reviews = parse_reviews(_FIXTURE_HTML, _SEL)
    # 본문 없는 마지막 블록은 제외 → 3건
    assert len(reviews) == 3

    r0 = reviews[0]
    assert r0.author_display == "김철수"
    assert r0.rating == 5
    assert r0.body.startswith("정말 맛있어요")
    assert r0.visited_at == date(2026, 7, 1)

    r1 = reviews[1]
    assert r1.rating == 2
    assert r1.visited_at == date(2026, 6, 28)

    # 별점/날짜 셀렉터가 매칭 안 되면 None
    r2 = reviews[2]
    assert r2.rating is None
    assert r2.visited_at is None


def test_parse_rating_from_aria_label():
    """별점이 텍스트가 아니라 aria-label 에만 있는 별 아이콘 위젯 케이스."""
    html = """
    <div class="review">
      <span class="name">최고객</span>
      <span class="star" aria-label="별점 4점"></span>
      <p class="text">aria-label 별점 테스트</p>
    </div>
    """
    reviews = parse_reviews(html, _SEL)
    assert reviews[0].rating == 4


def test_parse_empty_selector_raises():
    import pytest

    with pytest.raises(ValueError, match="비어 있습니다"):
        parse_reviews(_FIXTURE_HTML, {"review_item": "", "author": ".n", "body": ".t"})


# --------------------------- IncrementalStopTracker ---------------------------
def _r(body: str) -> RawReview:
    return RawReview(author_display="사용자", body=body, visited_at=date(2026, 7, 1))


def test_incremental_stops_after_two_consecutive_known_pages():
    old = [_r("old-1"), _r("old-2")]
    known = {dedup_key(x) for x in old}
    tracker = IncrementalStopTracker(known, stop_after_known=2)

    # 페이지1: 전부 신규 → 중단 아님
    assert tracker.add_page([_r("new-1"), _r("new-2")]) is False
    # 페이지2: 알려진 키 포함 → 연속 1, 중단 아님
    assert tracker.add_page([_r("new-3"), old[0]]) is False
    # 페이지3: 또 알려진 키 → 연속 2, 중단
    assert tracker.add_page([old[1]]) is True

    bodies = [r.body for r in tracker.new_reviews]
    assert bodies == ["new-1", "new-2", "new-3"]  # 신규만 누적, 중복 제외


def test_incremental_resets_on_fresh_page():
    known = {dedup_key(_r("old"))}
    tracker = IncrementalStopTracker(known, stop_after_known=2)
    assert tracker.add_page([_r("old")]) is False  # 연속 1
    assert tracker.add_page([_r("fresh")]) is False  # 신규 → 리셋
    assert tracker.add_page([_r("old")]) is False  # 다시 연속 1 (중단 아님)


def test_incremental_no_duplicates_with_accumulated_dom():
    """네이버 '더보기'는 같은 DOM 에 누적된다 — 매 반복 content 가 이전 리뷰를 다시 포함해도
    new_reviews 에 중복이 쌓이면 안 된다."""
    tracker = IncrementalStopTracker(known_keys=set(), stop_after_known=2)

    # 반복1: A,B / 반복2: A,B,C,D / 반복3: A,B,C,D,E (누적 DOM 시뮬레이션)
    tracker.add_page([_r("A"), _r("B")])
    tracker.add_page([_r("A"), _r("B"), _r("C"), _r("D")])
    tracker.add_page([_r("A"), _r("B"), _r("C"), _r("D"), _r("E")])

    assert [r.body for r in tracker.new_reviews] == ["A", "B", "C", "D", "E"]


# --------------------------- 스냅샷 저장/로테이션 ---------------------------
def test_snapshot_save_and_rotate(tmp_path):
    ch_id = 42
    p = save_snapshot(ch_id, "<html>a</html>", snapshot_dir=tmp_path)
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "<html>a</html>"

    # 8일 지난 파일로 mtime 조작 → 로테이션 대상
    old_file = save_snapshot(ch_id, "<html>old</html>", snapshot_dir=tmp_path)
    eight_days_ago = (datetime.now() - timedelta(days=8)).timestamp()
    os.utime(old_file, (eight_days_ago, eight_days_ago))

    removed = rotate_snapshots(ch_id, snapshot_dir=tmp_path, keep_days=7)
    assert removed == 1
    assert not old_file.exists()
    assert p.exists()  # 최근 파일은 유지


def test_rotate_all_cleans_orphan_channel_dirs(tmp_path):
    """삭제된 채널(DB에 없음)의 스냅샷 디렉토리도 파일시스템 기준 청소된다."""
    old_ts = (datetime.now() - timedelta(days=8)).timestamp()

    a = save_snapshot(1, "<html>a</html>", snapshot_dir=tmp_path)  # 살아있는 채널
    orphan = save_snapshot(999, "<html>orphan</html>", snapshot_dir=tmp_path)  # 고아
    os.utime(a, (old_ts, old_ts))
    os.utime(orphan, (old_ts, old_ts))
    fresh = save_snapshot(1, "<html>fresh</html>", snapshot_dir=tmp_path)

    removed = rotate_all_snapshots(snapshot_dir=tmp_path, keep_days=7)
    assert removed == 2
    assert not a.exists() and not orphan.exists()
    assert fresh.exists()
