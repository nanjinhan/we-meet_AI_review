"""네이버 플레이스 크롤러 (최대 리스크 — 방어적으로).

설계 (BACKEND.md §5, §11):
- Playwright(headless chromium)는 "페이지를 열고 '더보기'를 눌러 HTML을 얻는" 드라이버로만 쓴다.
- HTML → RawReview 변환(parse_reviews)과 증분 중단 판정(IncrementalStopTracker)은
  브라우저 없이 동작하는 순수 함수로 분리한다 → 저장된 HTML 픽스처로 파싱만 테스트 가능.
- CSS 셀렉터는 코드에 문자열로 두지 않고 selectors.yaml 에서만 읽는다 (CLAUDE.md 규칙 5).
- collector 는 실패 시 예외만 던진다. 지수 백오프 재시도는 worker 스케줄 레벨(T-06).

주: HTML 파싱에 beautifulsoup4 를 쓴다. BACKEND.md §0 의존성 목록엔 없지만, §11 의
"저장된 HTML 스냅샷 픽스처로 파싱만 테스트(라이브 크롤 금지)" 요구를 브라우저 없이
충족하기 위한 최소 추가다. 크롤러 엔진은 여전히 Playwright.
"""

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, RawReview, dedup_key
from app.config import settings
from app.models import StoreChannel

# backend/app/collectors/naver.py → parents[2] == backend/
_SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors.yaml"


def load_selectors(path: str | Path | None = None) -> dict:
    """selectors.yaml 의 naver 블록을 반환. 파일 없으면 즉시 에러."""
    p = Path(path) if path else _SELECTORS_PATH
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("naver", {})


def _require(sel: dict, keys: tuple[str, ...]) -> None:
    missing = [k for k in keys if not str(sel.get(k) or "").strip()]
    if missing:
        raise ValueError(
            f"selectors.yaml 의 naver 셀렉터가 비어 있습니다: {missing}. "
            "모바일 플레이스 페이지를 열어 값을 채우세요."
        )


def _parse_rating(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"[1-5]", text)
    return int(m.group()) if m else None


def _parse_visited(text: str | None) -> date | None:
    """'2026.7.1' / '2026-07-01' / '2026년 7월 1일' 등에서 YYYY M D 추출."""
    if not text:
        return None
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _text_or_aria(el) -> str | None:
    """요소의 텍스트, 비어 있으면 aria-label.

    별점 위젯은 aria-label 에만 숫자가 있는 경우가 흔하다.
    """
    if el is None:
        return None
    return el.get_text(strip=True) or el.get("aria-label") or None


def parse_reviews(html: str, sel: dict) -> list[RawReview]:
    """저장된 HTML → RawReview 목록. rating/visited_at 셀렉터가 비어 있으면 해당 필드는 None."""
    _require(sel, ("review_item", "author", "body"))
    soup = BeautifulSoup(html, "html.parser")
    reviews: list[RawReview] = []
    for item in soup.select(sel["review_item"]):
        author_el = item.select_one(sel["author"])
        body_el = item.select_one(sel["body"])
        body = body_el.get_text(strip=True) if body_el else ""
        if not body:
            continue  # 본문 없는 블록은 리뷰가 아님
        rating_sel = str(sel.get("rating") or "").strip()
        visited_sel = str(sel.get("visited_at") or "").strip()
        rating_el = item.select_one(rating_sel) if rating_sel else None
        visited_el = item.select_one(visited_sel) if visited_sel else None
        reviews.append(
            RawReview(
                author_display=author_el.get_text(strip=True) if author_el else "",
                rating=_parse_rating(_text_or_aria(rating_el)),
                body=body,
                visited_at=_parse_visited(_text_or_aria(visited_el)),
            )
        )
    return reviews


class IncrementalStopTracker:
    """증분 수집 중단 판정 (TECH_SPEC §3.2).

    최신순으로 페이지를 읽다가, 이미 저장된 dedup_key 를 만난 페이지가 stop_after_known 회
    '연속'되면 중단한다. 신규 리뷰만 new_reviews 에 누적한다.

    주의: 네이버 '더보기'는 같은 DOM 에 리뷰를 누적하므로 page.content() 는 매 반복마다
    이전 리뷰를 다시 포함한다 → 이번 크롤에서 이미 수집한 키(_seen)도 걸러야 중복이 없다.
    """

    def __init__(self, known_keys: set[str], stop_after_known: int = 2):
        self._known = known_keys
        self._limit = stop_after_known
        self._consecutive_known = 0
        self._seen: set[str] = set()  # 이번 크롤에서 이미 수집한 신규 리뷰 키
        self.new_reviews: list[RawReview] = []

    def add_page(self, page_reviews: list[RawReview]) -> bool:
        """페이지를 반영하고 '이제 중단해야 하는가'를 반환."""
        hit_known = False
        for r in page_reviews:
            key = dedup_key(r)
            if key in self._known:
                hit_known = True
            elif key not in self._seen:
                self._seen.add(key)
                self.new_reviews.append(r)
        if hit_known:
            self._consecutive_known += 1
        else:
            self._consecutive_known = 0
        return self._consecutive_known >= self._limit


def save_snapshot(
    channel_id: int, html: str, snapshot_dir: str | Path | None = None, now: datetime | None = None
) -> Path:
    """페이지 HTML 을 {snapshot_dir}/{channel_id}/{ts}.html 로 저장 (디버깅용, 7일 보관)."""
    now = now or datetime.now()
    base = Path(snapshot_dir or settings.snapshot_dir) / str(channel_id)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{now.strftime('%Y%m%dT%H%M%S%f')}.html"
    path.write_text(html, encoding="utf-8")
    return path


def _rotate_dir(base: Path, keep_days: int, now: datetime | None) -> int:
    now = now or datetime.now()
    if not base.exists():
        return 0
    cutoff = (now - timedelta(days=keep_days)).timestamp()
    removed = 0
    for f in base.glob("*.html"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed


def rotate_snapshots(
    channel_id: int,
    snapshot_dir: str | Path | None = None,
    keep_days: int = 7,
    now: datetime | None = None,
) -> int:
    """한 채널의 7일 지난 스냅샷 삭제. 삭제한 파일 수 반환."""
    base = Path(snapshot_dir or settings.snapshot_dir) / str(channel_id)
    return _rotate_dir(base, keep_days, now)


def rotate_all_snapshots(
    snapshot_dir: str | Path | None = None,
    keep_days: int = 7,
    now: datetime | None = None,
) -> int:
    """스냅샷 루트 전체 로테이션. 파일시스템 기준이라 삭제된 채널의 고아 디렉토리도 청소된다."""
    root = Path(snapshot_dir or settings.snapshot_dir)
    if not root.exists():
        return 0
    removed = 0
    for child in root.iterdir():
        if child.is_dir():
            removed += _rotate_dir(child, keep_days, now)
    return removed


class NaverCollector(BaseCollector):
    """Playwright 로 모바일 플레이스 리뷰를 증분 수집한다. 인스턴스 1개 순차 처리."""

    def __init__(
        self, selectors: dict | None = None, snapshot_dir: str | Path | None = None
    ):
        self._sel = selectors if selectors is not None else load_selectors()
        self._snapshot_dir = snapshot_dir or settings.snapshot_dir

    async def collect(
        self,
        channel: StoreChannel,
        stop_after_known: int = 2,
        known_keys: set[str] | None = None,
        max_pages: int = 50,
    ) -> list[RawReview]:
        _require(self._sel, ("review_item", "author", "body", "more_button"))
        if not channel.external_url:
            raise ValueError("네이버 채널에 external_url 이 없습니다.")

        # Playwright 는 여기서만 import (모듈 로드시 브라우저 의존성 회피 — 테스트 경량화).
        from playwright.async_api import async_playwright

        tracker = IncrementalStopTracker(known_keys or set(), stop_after_known)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(channel.external_url, wait_until="domcontentloaded")
                for _ in range(max_pages):
                    html = await page.content()
                    save_snapshot(channel.id, html, self._snapshot_dir)
                    if tracker.add_page(parse_reviews(html, self._sel)):
                        break
                    more = page.locator(self._sel["more_button"])
                    if await more.count() == 0 or not await more.first.is_enabled():
                        break  # 더 이상 페이지 없음
                    await more.first.click()
                    await page.wait_for_timeout(800)  # 로딩 대기
            finally:
                await browser.close()

        rotate_snapshots(channel.id, self._snapshot_dir)
        return tracker.new_reviews
