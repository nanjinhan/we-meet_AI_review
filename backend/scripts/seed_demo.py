"""데모 시드 (T-15) — LLM 호출 없이 전 화면이 동작하는 데이터를 넣는다.

- 가상 매장 2 + 경쟁매장 2(자체 stores 행, is_competitor 채널로 연결)
- 리뷰 ~370건(최근 16주 분산) + 규칙 기반 분석(review_analysis) + 답글 일부 승인
- weekly_aspect_stats 는 실제 파이프라인(upsert_week_stats)으로 재집계 → 대시보드/비교와 정합
- 주간 리포트 2건, 긴급 알림 소량

근거 진단용 데이터(2026-11 추가):
- 리뷰 본문은 문장 조각을 조합해 만든다(_compose) — 항목마다 **근거 문장(quote)** 이 원문 그대로
  들어가고, 긴 문장은 매장 안에서 겹치지 않는다. 그래서 '같은 문장 반복' 검토 신호에는 아래에서
  일부러 넣은 사례만 잡힌다.
- 첫 매장에는 화면 설명용 사례를 넣는다(_seed_showcase): 같은 문장을 쓴 리뷰 3건, CSV 로 한 번 더
  들어온 중복 기록 2건, 점주가 제외한 리뷰 1건, 분석 전/실패/작성일 없음 각 1건, 실행 과제 2건.

실행:  cd backend && python -m scripts.seed_demo
재실행하면 데모 소유자(DEV_USER_ID)의 기존 데이터를 지우고 새로 넣는다(멱등).
프론트 개발모드 토큰의 sub 도 DEV_USER_ID 와 같아야 한다 (frontend/.env.local 참고).
"""

import asyncio
import random
import sys
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, text

from app.db import SessionLocal
from app.models import (
    ActionItem,
    Alert,
    Reply,
    Report,
    Review,
    ReviewAnalysis,
    Store,
    StoreChannel,
    StoreSettings,
)
from app.pipeline.stats import upsert_week_stats, week_start_of
from app.services.insights import SIMILAR_MIN_LEN
from app.services.review_text import long_units
from app.services.sufficiency import ISSUE_MIN_RELATED, OBSERVATION_MIN_ANALYZED

DEV_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
WEEKS = 16  # 오늘 포함 과거 16주에 리뷰 분산 (4w/8w 대시보드 delta 까지 유효)

rng = random.Random(20260723)

AUTHORS = ["김**", "이**", "박**", "최**", "정**", "한**", "윤**", "장**", "임**", "서**"]

# ---------------------------------------------------------------------------
# 리뷰 본문 조립용 문장 조각.
# (항목, 문장 틀, 슬롯 후보, 키워드) — 문장 하나가 곧 그 항목의 근거 문장(quote)이 된다.
# {menu} 는 매장 종류별 메뉴로 채운다.
# ---------------------------------------------------------------------------
CAFE, KOREAN = "cafe", "korean"

MENUS = {
    CAFE: [
        "브런치 플레이트가", "크로플이", "바닐라 라떼가", "프렌치토스트가",
        "에그 베네딕트가", "당근 케이크가", "플랫화이트가", "잠봉뵈르 샌드위치가",
    ],
    KOREAN: [
        "김치찜이", "묵은지 김치찜이", "계란말이가", "제육볶음이",
        "된장찌개가", "수육이", "밑반찬이", "돌솥밥이",
    ],
}
# 맛 불만 표현은 업종에 맞게 (카페=달다, 한식=짜다)
TASTE_OFF = {CAFE: ("너무 달았어요", "달다"), KOREAN: ("너무 짰어요", "짜다")}

WHEN = ["평일 점심에", "주말 오후에", "토요일 저녁에", "일요일 낮에", "퇴근하고", "오픈 시간에"]

POS_CORES = [
    ("맛", "{menu} {adv} 맛있었어요", {"adv": ["정말", "진짜", "기대 이상으로", "소문대로"]}, []),
    ("맛", "{menu} 또 생각날 것 같아요", {}, []),
    ("맛", "재료가 신선한 게 느껴져요", {}, []),
    ("친절", "사장님이 {adv} 친절하세요", {"adv": ["너무", "정말", "항상", "늘"]}, []),
    (
        "친절",
        "직원분들이 {how} 챙겨주셨어요",
        {"how": ["세심하게", "먼저 다가와서", "웃으면서", "바쁜데도 꼼꼼히"]},
        [],
    ),
    ("청결", "매장이 {scope} 깔끔해요", {"scope": ["전체적으로", "구석구석", "화장실까지"]}, []),
    (
        "분위기",
        "분위기가 {why} 좋아요",
        {"why": ["조용해서", "아늑해서", "감성적이라", "햇살이 잘 들어서"]},
        [],
    ),
    (
        "분위기",
        "{who} 오기 좋은 곳이에요",
        {"who": ["친구랑", "부모님 모시고", "아이들과", "혼자"]},
        [],
    ),
    ("가격", "가성비가 좋아요", {}, []),
    ("가격", "이 가격에 이 정도면 만족해요", {}, []),
    ("대기시간", "{when} 갔는데 웨이팅 없이 바로 앉았어요", {"when": WHEN}, []),
    (
        "대기시간",
        "음식이 {speed} 나왔어요",
        {"speed": ["금방", "생각보다 빨리", "주문하고 10분 만에"]},
        [],
    ),
]

NEG_CORES = [
    (
        "대기시간",
        "{when} 갔는데 웨이팅이 {dur} 걸렸어요",
        {"when": WHEN, "dur": ["40분 넘게", "1시간 가까이", "1시간 넘게", "50분이나", "30분 넘게"]},
        ["웨이팅"],
    ),
    (
        "대기시간",
        "주문하고 음식 나오는 데 {dur} 걸렸어요",
        {"dur": ["30분이나", "40분 가까이", "한참"]},
        ["대기"],
    ),
    (
        "대기시간",
        "주문이 누락돼서 {dur} 더 기다렸어요",
        {"dur": ["20분을", "30분을", "한참을"]},
        ["주문누락"],
    ),
    (
        "친절",
        "{who} 불친절해서 기분이 상했어요",
        {"who": ["직원이", "계산하시는 분이", "서빙하시는 분이"]},
        ["불친절"],
    ),
    (
        "친절",
        "질문했는데 {how} 대답해서 민망했어요",
        {"how": ["퉁명스럽게", "귀찮다는 듯이", "쳐다보지도 않고"]},
        ["불친절"],
    ),
    (
        "청결",
        "{where} 끈적해서 불쾌했어요",
        {"where": ["테이블이", "바닥이", "메뉴판이"]},
        ["위생"],
    ),
    (
        "청결",
        "{thing}에서 머리카락이 나왔어요",
        {"thing": ["음식", "컵", "접시"]},
        ["위생", "이물질"],
    ),
    ("가격", "가격이 {change} 올랐네요", {"change": ["갑자기", "또", "지난번보다"]}, ["가격인상"]),
    ("가격", "양에 비해 가격이 비싼 편이에요", {}, ["가격", "양"]),
    ("맛", "{menu} {taste_off}", {}, ["{taste_kw}"]),
    ("맛", "음식이 식어서 나왔어요", {}, ["식은음식"]),
    ("기타", "주차할 곳이 없어서 {dur} 헤맸어요", {"dur": ["한참", "20분을", "골목을"]}, ["주차"]),
    (
        "분위기",
        "{what} 시끄러워서 대화가 힘들었어요",
        {"what": ["음악이", "옆 테이블이", "매장이"]},
        ["소음"],
    ),
]

NEU_LINES = ["무난했어요", "평범한 동네 가게 느낌이에요", "나쁘지 않았어요", "그럭저럭이에요"]
POS_CLOSINGS = ["", "", "추천합니다", "또 올게요", "재방문 의사 있어요", "단골 될 것 같아요"]
NEG_CLOSINGS = ["", "", "아쉽네요", "개선됐으면 좋겠어요", "다시 갈지는 모르겠어요"]

# 매장마다 불만·호평이 몰리는 항목을 다르게 — 화면에서 '이 매장의 반복 문제'가 보이도록.
NEG_WEIGHTS = {
    CAFE: {"대기시간": 9, "청결": 4, "친절": 1, "분위기": 1, "가격": 1, "맛": 1, "기타": 1},
    KOREAN: {"가격": 9, "맛": 3, "친절": 1, "대기시간": 1, "청결": 1, "기타": 1, "분위기": 1},
}
POS_WEIGHTS = {
    CAFE: {"분위기": 4, "맛": 4, "친절": 2, "청결": 2, "가격": 1, "대기시간": 1},
    KOREAN: {"맛": 5, "친절": 3, "가격": 2, "청결": 1, "분위기": 1, "대기시간": 1},
}

REPLY_TEMPLATES = {
    "pos": "소중한 리뷰 감사합니다! 다음에 오실 때도 만족하실 수 있도록 늘 노력하겠습니다. :)",
    "neu": "방문해 주셔서 감사합니다. 말씀 주신 부분 참고해서 더 나아지는 모습 보여드리겠습니다.",
    "neg": (
        "불편을 드려 정말 죄송합니다. 말씀 주신 내용은 바로 개선하겠습니다. "
        "다시 기회를 주시면 좋은 모습으로 보답하겠습니다."
    ),
}

STORES = [
    # (이름, 카테고리, 주소, 종류, 주간 리뷰수 범위, 긍정확률(시작→끝: 추세))
    # 첫 매장: 호평이 많지만 대기 불만이 여러 주에 걸쳐 남아 있는 가게 — 근거 진단 설명용.
    ("성수 브런치카페 온도", "카페", "서울 성동구 성수동 12-3", CAFE, (5, 9), (0.52, 0.66)),
    ("망원 김치찜 온기", "한식", "서울 마포구 망원동 44-1", KOREAN, (4, 8), (0.70, 0.58)),
]
COMPETITORS = [
    # (이름, 카테고리, 연결할 내 매장 인덱스, 종류, 주간 리뷰수 범위, 긍정확률)
    ("성수 카페 클라우드", "카페", 0, CAFE, (3, 6), (0.65, 0.65)),
    ("망원 김치찜 명가", "한식", 1, KOREAN, (3, 6), (0.72, 0.72)),
]


def _diag(
    level: str, title: str, evidence: str, aspect: str | None = None, polarity: str | None = None
) -> dict:
    """aspect/polarity 가 있으면 리포트 카드에서 그 항목의 근거 리뷰로 연결된다."""
    item = {"level": level, "title": title, "evidence": evidence}
    if aspect and polarity:
        item |= {"aspect": aspect, "polarity": polarity}
    return item


def _rx(title: str, detail: str, effect: str) -> dict:
    return {"title": title, "detail": detail, "expected_effect": effect}


# 시드 리포트는 수치를 직접 쓰지 않는다(실제 건수는 실행 시점마다 달라지므로).
# 건수는 카드의 '근거 리뷰 보기'로 연결되는 근거 화면에서 확인한다.
# 원인은 단정하지 않고, 예상 효과는 '기대'로 적는다(report_v2 가드레일과 같은 톤).
REPORTS = {
    0: (
        [
            _diag(
                "crit",
                "웨이팅 불만이 여러 주에 걸쳐 반복",
                "최근 4주 '대기시간' 불만 언급이 이어지고 '웨이팅' 키워드가 상위",
                "대기시간",
                "neg",
            ),
            _diag(
                "warn",
                "위생 관련 지적이 이어짐",
                "'청결' 불만 언급이 여러 주에 발생",
                "청결",
                "neg",
            ),
            _diag(
                "strength",
                "맛에 대한 호평이 꾸준함",
                "'맛' 호평 언급이 매주 확인됨",
                "맛",
                "pos",
            ),
            _diag(
                "opportunity",
                "분위기 호평을 홍보에 활용할 여지",
                "'분위기' 호평 언급이 꾸준히 확인됨",
                "분위기",
                "pos",
            ),
        ],
        [
            _rx(
                "예상 대기시간 안내 개선 검토",
                "피크 시간대 실제 대기 기록을 먼저 확인하고, 입구·네이버 공지에 예상 대기시간 안내",
                "대기 관련 불만 언급 감소 기대",
            ),
            _rx(
                "마감 청소 체크리스트 운영",
                "리뷰에서 지적된 위치(테이블·바닥·메뉴판)를 점검 항목에 추가",
                "같은 위치의 위생 지적 재발 방지 기대",
            ),
            _rx(
                "포토존 해시태그 이벤트",
                "분위기 호평이 많은 자리를 포토존으로 안내",
                "신규 방문 유입 가능성",
            ),
        ],
    ),
    1: (
        [
            _diag(
                "crit",
                "가격 관련 불만 언급이 늘어남",
                "'가격' 불만 언급과 '가격인상' 키워드가 상위",
                "가격",
                "neg",
            ),
            _diag("warn", "긍정 비율이 내려가는 추세", "긍정 비율이 직전 기간보다 낮아짐"),
            _diag(
                "strength",
                "맛에 대한 호평은 유지",
                "'맛' 호평 언급이 꾸준히 확인됨",
                "맛",
                "pos",
            ),
            _diag(
                "opportunity",
                "응대 호평을 단골 관리로 연결할 여지",
                "'친절' 호평 언급이 꾸준히 확인됨",
                "친절",
                "pos",
            ),
        ],
        [
            _rx(
                "점심 한정 세트 메뉴 검토",
                "김치찜+공기밥+음료 구성으로 체감 가격을 낮추는 방안",
                "가격 불만 언급 완화 기대",
            ),
            _rx(
                "가격 조정 사유 안내문 게시",
                "원재료 가격 변동을 매장·네이버 공지에 안내",
                "가격 관련 오해 감소 기대",
            ),
            _rx("재방문 스탬프 쿠폰", "5회 방문 시 1인분 무료", "단골 재방문 유도 가능성"),
        ],
    ),
}


def _fill(core: tuple, kind: str) -> tuple[str, str, list[str]]:
    """문장 조각 하나를 실제 문장으로. (항목, 문장, 키워드) 반환."""
    category, template, slots, keywords = core
    taste_off, taste_kw = TASTE_OFF[kind]
    values = {name: rng.choice(options) for name, options in slots.items()}
    values |= {"menu": rng.choice(MENUS[kind]), "taste_off": taste_off}
    sentence = template.format(**values)
    return category, sentence, [k.replace("{taste_kw}", taste_kw) for k in keywords]


def _pick_cores(
    cores: list[tuple], weights: dict[str, int], n: int, exclude: tuple[str, ...] = ()
) -> list[tuple]:
    """서로 다른 항목의 문장 조각 n개를 가중치대로 뽑는다. exclude 항목은 건너뛴다."""
    picked: list[tuple] = []
    pool = [c for c in cores if c[0] not in exclude]
    for _ in range(n):
        if not pool:
            break
        core = rng.choices(pool, weights=[weights.get(c[0], 1) for c in pool])[0]
        picked.append(core)
        pool = [c for c in pool if c[0] != core[0]]
    return picked


def _draft(sentiment: str, kind: str) -> dict:
    """리뷰 1건의 초안: 본문 + 항목별 근거 문장 + 키워드 + 평점."""
    aspects: list[dict] = []
    keywords: list[str] = []
    sentences: list[str] = []

    def add(core: tuple, polarity: str, prefix: str = "") -> None:
        category, sentence, kws = _fill(core, kind)
        sentences.append(prefix + sentence)
        aspects.append({"category": category, "polarity": polarity, "quote": sentence})
        keywords.extend(k for k in kws if k not in keywords)

    def mentioned() -> tuple[str, ...]:
        return tuple(a["category"] for a in aspects)

    if sentiment == "pos":
        for core in _pick_cores(POS_CORES, POS_WEIGHTS[kind], rng.choice([1, 1, 2, 2, 3])):
            add(core, "pos")
        closing, rating = rng.choice(POS_CLOSINGS), rng.randint(4, 5)
    elif sentiment == "neg":
        for core in _pick_cores(NEG_CORES, NEG_WEIGHTS[kind], rng.choice([1, 1, 1, 2])):
            add(core, "neg")
        if rng.random() < 0.25:  # 불만 속에 다른 항목의 호평이 섞인 리뷰
            add(_pick_cores(POS_CORES, POS_WEIGHTS[kind], 1, mentioned())[0], "pos", "그래도 ")
        closing = rng.choice(NEG_CLOSINGS)
        rating = 1 if "이물질" in keywords else rng.randint(1, 3)
    else:
        if rng.random() < 0.5:
            sentences.append(rng.choice(NEU_LINES))
        else:  # 좋은 점과 아쉬운 점을 함께 적은 중립 리뷰
            add(_pick_cores(POS_CORES, POS_WEIGHTS[kind], 1)[0], "pos")
            add(_pick_cores(NEG_CORES, NEG_WEIGHTS[kind], 1, mentioned())[0], "neg", "다만 ")
        closing, rating = "", rng.randint(3, 4)

    if closing:
        sentences.append(closing)
    body = ". ".join(sentences) + rng.choice([".", ".", "!"])
    return {"body": body, "aspects": aspects, "keywords": keywords, "rating": rating}


def _compose(sentiment: str, kind: str, used: set[str]) -> dict:
    """매장 안에서 긴 문장·본문이 겹치지 않는 리뷰 초안.

    '같은 문장 반복' 검토 신호(insights.find_review_checks)와 같은 기준(long_units)으로 확인한다 —
    조합이 우연히 겹쳐 시드 전체가 검토 대상으로 잡히는 일을 막는다.
    """
    for _ in range(60):
        draft = _draft(sentiment, kind)
        keys = {key for key, _ in long_units(draft["body"], SIMILAR_MIN_LEN)}
        if not keys & used:
            break
    used |= keys
    return draft


def _severity(sentiment: str, rating: int, keywords: list[str]) -> tuple[str, bool]:
    if sentiment != "neg":
        return "normal", False
    if rating <= 1 or "이물질" in keywords:
        return "complaint", True  # 긴급
    if rating == 2:
        return "complaint", False
    return "uncomfortable", False


async def _wipe(db) -> None:
    """데모 소유자의 기존 매장(경쟁매장 포함)을 통째로 삭제 — FK cascade 로 하위 데이터까지."""
    ids = list(
        (await db.execute(select(Store.id).where(Store.owner_id == DEV_USER_ID))).scalars()
    )
    if ids:
        # competitor_of 가 stores 를 참조(SET NULL 아님)하므로 채널 먼저 제거
        await db.execute(delete(StoreChannel).where(StoreChannel.store_id.in_(ids)))
        await db.execute(delete(Store).where(Store.id.in_(ids)))


async def _add_review(
    db,
    channel_id: int,
    key: str,
    draft: dict,
    sentiment: str | None,
    written: date | None,
    *,
    author: str | None,
    analysis: str = "ok",  # ok / none(분석 전) / failed
    reply: bool = False,
    excluded_reason: str | None = None,
) -> dict:
    """리뷰 1건(+분석, +답글) 삽입. 이후 단계에서 쓸 수 있게 원본 정보를 함께 반환."""
    review = Review(
        channel_id=channel_id,
        dedup_key=key,
        author_masked=author,
        rating=draft["rating"],
        body=draft["body"],
        written_at=written,
        excluded_at=datetime.now(UTC) if excluded_reason else None,
        exclude_reason=excluded_reason,
    )
    db.add(review)
    await db.flush()

    urgent = False
    if analysis == "failed":
        db.add(ReviewAnalysis(review_id=review.id, model_ver="failed"))
    elif analysis == "ok":
        severity, urgent = _severity(sentiment, draft["rating"], draft["keywords"])
        db.add(
            ReviewAnalysis(
                review_id=review.id,
                sentiment=sentiment,
                severity=severity,
                urgent=urgent,
                aspects=draft["aspects"],
                keywords=draft["keywords"],
                model_ver="seed-v2",
                alerted_at=datetime.now(UTC) if urgent else None,
            )
        )
    if reply:
        db.add(
            Reply(
                review_id=review.id,
                tone="apologetic" if sentiment == "neg" else "polite",
                draft=REPLY_TEMPLATES[sentiment],
                status="approved",
                approved_at=datetime.now(UTC),
            )
        )
    return {"review": review, "sentiment": sentiment, "urgent": urgent, "draft": draft}


async def _seed_store_reviews(
    db, channel_id: int, kind: str, weeks_cfg, pos_cfg, *, with_replies: bool
) -> list[dict]:
    """한 채널에 WEEKS 주 분량 리뷰+분석(+답글) 삽입. 삽입한 리뷰 정보 목록 반환(최근 주 먼저)."""
    lo, hi = weeks_cfg
    p_start, p_end = pos_cfg
    today = datetime.now(UTC).date()
    used: set[str] = set()  # 이 매장에서 이미 쓴 긴 문장·본문(정규화 키)
    out: list[dict] = []
    seq = 0
    for w in range(WEEKS):
        # w=WEEKS-1 이 가장 과거. 긍정확률은 과거→현재 선형 보간(추세 연출).
        t = 1 - w / max(WEEKS - 1, 1)
        p_pos = p_start + (p_end - p_start) * t
        week_monday = week_start_of(today) - timedelta(weeks=w)
        for _ in range(rng.randint(lo, hi)):
            seq += 1
            r = rng.random()
            sentiment = "pos" if r < p_pos else ("neu" if r < p_pos + 0.15 else "neg")
            written = min(week_monday + timedelta(days=rng.randint(0, 6)), today)
            out.append(
                await _add_review(
                    db,
                    channel_id,
                    f"seed-{channel_id}-{seq}",
                    _compose(sentiment, kind, used),
                    sentiment,
                    written,
                    author=rng.choice(AUTHORS),
                    # 내 매장 리뷰 70% 는 승인된 답글 보유 → 답변율이 살아있는 화면
                    reply=with_replies and rng.random() < 0.7,
                )
            )
    return out


def _action_start(rows: list[dict], aspect: str, today: date) -> date:
    """실행 과제의 실행일을 데이터에 맞춰 고른다.

    '불만이 반복돼서 과제를 골랐고, 그 뒤 리뷰를 지켜보는 중'이라는 흐름이 보이도록
    실행 전 4주에 그 항목 불만이 '반복' 기준 이상이면서 실행 후 리뷰도 관측 기준 이상 쌓인
    가장 최근 날짜를 고른다(3일 전부터 4주 전까지 훑는다). 맞는 날이 없으면 실행 전 불만이
    가장 많은 날. 시드를 실행하는 요일에 따라 리뷰 날짜가 달라져도 흐름이 유지된다.
    실행 후 건수는 손대지 않는다 — 관측 결과는 있는 그대로 보여준다.
    """
    all_dates = [r["review"].written_at for r in rows]
    dates = [
        r["review"].written_at
        for r in rows
        if any(a["category"] == aspect and a["polarity"] == "neg" for a in r["draft"]["aspects"])
    ]
    best, best_before = today - timedelta(days=10), -1
    for days_ago in range(3, 29):
        start = today - timedelta(days=days_ago)
        before = sum(1 for d in dates if start - timedelta(days=28) <= d < start)
        after = sum(1 for d in all_dates if d >= start)
        if before >= ISSUE_MIN_RELATED and after >= OBSERVATION_MIN_ANALYZED:
            return start
        if before > best_before:
            best, best_before = start, before
    return best


SAME_SENTENCE = "사장님이 정말 친절하시고 음식도 맛있어서 다음에 또 방문할게요"


async def _seed_showcase(db, store: Store, naver_channel: StoreChannel, rows: list[dict]) -> dict:
    """첫 매장에 근거 진단 화면 설명용 사례를 넣는다. 넣은 건수 요약을 반환.

    전부 '사람이 확인할 거리'다 — 시드도 실제 서비스처럼 아무것도 자동으로 판정하지 않는다.
    """
    today = datetime.now(UTC).date()
    key = iter(f"seed-show-{store.id}-{n}" for n in range(100))

    # 1) 서로 다른 작성자가 같은 긴 문장을 쓴 리뷰 3건 → '같은 문장 반복' 검토 신호
    same_aspects = [
        {"category": "친절", "polarity": "pos", "quote": "사장님이 정말 친절하시고"},
        {"category": "맛", "polarity": "pos", "quote": "음식도 맛있어서"},
    ]
    for author, days_ago, body in [
        ("김**", 9, SAME_SENTENCE + "!"),
        ("이**", 6, "첫 방문이에요. " + SAME_SENTENCE + "."),
        ("박**", 2, SAME_SENTENCE),
    ]:
        draft = {"body": body, "aspects": same_aspects, "keywords": [], "rating": 5}
        await _add_review(db, naver_channel.id, next(key), draft, "pos",
                          today - timedelta(days=days_ago), author=author)

    # 2) 같은 리뷰가 CSV 업로드로 한 번 더 들어온 경우 → '중복 기록' 검토 신호.
    #    (크롤러 장애 때 CSV 로 올렸다가 크롤러가 복구되면 실제로 생기는 상황)
    csv_channel = StoreChannel(store_id=store.id, platform="csv")
    db.add(csv_channel)
    await db.flush()
    #    최근 10일 안에서 가장 오래된 것을 고른다 — 근거 목록 맨 위가 같은 글 두 줄로 시작하지 않게.
    recent = sorted(
        (r for r in rows if r["review"].written_at >= today - timedelta(days=10)),
        key=lambda r: (r["review"].written_at, r["review"].id),
    )
    picks = [r for r in recent if r["sentiment"] == "neg"][:1]
    picks += [r for r in recent if r["sentiment"] == "pos"][:1]
    for src in picks:
        await _add_review(db, csv_channel.id, next(key), src["draft"], src["sentiment"],
                          src["review"].written_at, author=None)  # CSV 에 작성자 열 없음

    # 3) 점주가 이유를 남기고 분석에서 제외한 리뷰 → '제외 내역'
    draft = {"body": "건너편 카페 후기를 여기에 잘못 올렸네요. 죄송합니다.",
             "aspects": [], "keywords": [], "rating": 3}
    await _add_review(db, naver_channel.id, next(key), draft, "neu", today - timedelta(days=12),
                      author="최**", excluded_reason="우리 매장과 무관한 내용")

    # 4) 분석 범위의 '누락' 표시용: 분석 전 1건 / 분석 실패 1건 / 작성일 없음 1건
    draft = {"body": "오늘 다녀왔어요. 브런치 플레이트 양이 푸짐했고 자리도 넓었어요.",
             "aspects": [], "keywords": [], "rating": 4}
    await _add_review(db, naver_channel.id, next(key), draft, None, today,
                      author="정**", analysis="none")
    draft = {"body": "사진만 올리려다 글도 남겨요. 다음에 또 올게요.",
             "aspects": [], "keywords": [], "rating": 4}
    await _add_review(db, naver_channel.id, next(key), draft, None, today - timedelta(days=1),
                      author="한**", analysis="failed")
    draft = {"body": "예전에 받은 후기를 옮겨 적었습니다. 커피가 맛있었어요.",
             "aspects": [{"category": "맛", "polarity": "pos", "quote": "커피가 맛있었어요"}],
             "keywords": [], "rating": 4}
    await _add_review(db, csv_channel.id, next(key), draft, "pos", None, author=None)

    # 5) 실행 과제 — 근거를 보고 고른 행동과 실행일(이후 리뷰 관측의 기준)
    db.add(ActionItem(
        store_id=store.id, aspect="대기시간", polarity="neg",
        title="예상 대기시간 안내판 설치",
        note="피크 시간대 대기 기록을 적어 본 뒤, 입구와 네이버 공지에 함께 안내",
        started_on=_action_start(rows, "대기시간", today),
    ))
    db.add(ActionItem(
        store_id=store.id, aspect="청결", polarity="neg",
        title="마감 청소 체크리스트 운영",
        note="테이블·바닥·메뉴판을 점검 항목에 추가",
        started_on=today - timedelta(days=42), status="done",
    ))
    return {"same_sentence": 3, "duplicates": len(picks), "excluded": 1, "missing": 3, "actions": 2}


async def main() -> None:
    async with SessionLocal() as db:
        await db.execute(
            text("insert into auth.users (id) values (:uid) on conflict do nothing"),
            {"uid": DEV_USER_ID},
        )
        await _wipe(db)

        today = datetime.now(UTC).date()
        all_store_ids: list[int] = []
        my_stores: list[Store] = []
        total_reviews = 0
        total_urgent = 0
        showcase: dict = {}

        for idx, (name, category, address, kind, weeks_cfg, pos_cfg) in enumerate(STORES):
            store = Store(owner_id=DEV_USER_ID, name=name, category=category, address=address)
            db.add(store)
            await db.flush()
            db.add(StoreSettings(store_id=store.id))
            channel = StoreChannel(
                store_id=store.id,
                platform="naver",
                external_url=f"https://map.naver.com/p/entry/place/demo-{store.id}",
            )
            db.add(channel)
            await db.flush()
            rows = await _seed_store_reviews(
                db, channel.id, kind, weeks_cfg, pos_cfg, with_replies=True
            )
            total_reviews += len(rows)

            # 긴급 리뷰 → alerts (최근 것 위주 2건). rows 는 최근 주가 먼저다.
            urgent_rows = [r["review"] for r in rows if r["urgent"]]
            for rv in urgent_rows[:2]:
                db.add(
                    Alert(
                        store_id=store.id,
                        review_id=rv.id,
                        kind="urgent_review",
                        sent_via=["mock"],
                    )
                )
                total_urgent += 1

            if idx == 0:
                showcase = await _seed_showcase(db, store, channel, rows)
                total_reviews += (
                    showcase["same_sentence"] + showcase["duplicates"]
                    + showcase["excluded"] + showcase["missing"]
                )
            else:
                db.add(ActionItem(
                    store_id=store.id, aspect="가격", polarity="neg",
                    title="가격 조정 사유 안내문 게시",
                    note="원재료 가격 변동을 매장 입구와 네이버 공지에 안내",
                    started_on=_action_start(rows, "가격", today),
                ))

            my_stores.append(store)
            all_store_ids.append(store.id)

        for name, category, my_idx, kind, weeks_cfg, pos_cfg in COMPETITORS:
            comp = Store(owner_id=DEV_USER_ID, name=name, category=category, address=None)
            db.add(comp)
            await db.flush()
            channel = StoreChannel(
                store_id=comp.id,
                platform="naver",
                external_url=f"https://map.naver.com/p/entry/place/demo-{comp.id}",
                is_competitor=True,
                competitor_of=my_stores[my_idx].id,
            )
            db.add(channel)
            await db.flush()
            rows = await _seed_store_reviews(
                db, channel.id, kind, weeks_cfg, pos_cfg, with_replies=False
            )
            total_reviews += len(rows)
            all_store_ids.append(comp.id)

        # 주간 집계는 실제 파이프라인으로 (대시보드·비교와 정합 보장)
        for sid in all_store_ids:
            for w in range(WEEKS):
                await upsert_week_stats(db, sid, week_start_of(today) - timedelta(weeks=w))

        # 주간 리포트 (지난주 기준)
        last_week = week_start_of(today) - timedelta(weeks=1)
        for idx, store in enumerate(my_stores):
            diagnosis, prescriptions = REPORTS[idx]
            db.add(
                Report(
                    store_id=store.id,
                    week_start=last_week,
                    diagnosis=diagnosis,
                    prescriptions=prescriptions,
                )
            )

        await db.commit()

        print(f"시드 완료: 매장 {len(STORES)} + 경쟁 {len(COMPETITORS)}, "
              f"리뷰 {total_reviews}건, 긴급알림 {total_urgent}건, 리포트 {len(my_stores)}건")
        print(f"근거 진단 사례({STORES[0][0]}): 같은 문장 {showcase['same_sentence']}건, "
              f"중복 기록 {showcase['duplicates']}건, 제외 {showcase['excluded']}건, "
              f"분석 전·실패·작성일 없음 {showcase['missing']}건, "
              f"실행 과제 {showcase['actions']}건")
        print(f"데모 소유자(sub): {DEV_USER_ID}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
