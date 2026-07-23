"""데모 시드 (T-15) — LLM 호출 없이 전 화면이 동작하는 데이터를 넣는다.

- 가상 매장 2 + 경쟁매장 2(자체 stores 행, is_competitor 채널로 연결)
- 리뷰 ~300건(최근 16주 분산) + 규칙 기반 분석(review_analysis) + 답글 일부 승인
- weekly_aspect_stats 는 실제 파이프라인(upsert_week_stats)으로 재집계 → 대시보드/비교와 정합
- 주간 리포트 2건, 긴급 알림 소량

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
    Alert,
    Reply,
    Review,
    ReviewAnalysis,
    Store,
    StoreChannel,
    StoreSettings,
    Report,
)
from app.pipeline.stats import upsert_week_stats, week_start_of

DEV_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
WEEKS = 16  # 오늘 포함 과거 16주에 리뷰 분산 (4w/8w 대시보드 delta 까지 유효)

rng = random.Random(20260723)

AUTHORS = ["김**", "이**", "박**", "최**", "정**", "한**", "윤**", "장**", "임**", "서**"]

# (본문, aspects[(category, polarity)], keywords, 평점범위)
POS_TEMPLATES = [
    ("음식이 정말 맛있어요. 재료가 신선한 게 느껴집니다.", [("맛", "pos")], [], (4, 5)),
    ("사장님이 너무 친절하세요. 기분 좋게 먹고 갑니다.", [("친절", "pos")], [], (5, 5)),
    ("매장이 깔끔하고 분위기가 좋아요. 데이트 코스로 추천!", [("청결", "pos"), ("분위기", "pos")], [], (4, 5)),
    ("가성비 최고예요. 이 가격에 이 퀄리티라니.", [("가격", "pos"), ("맛", "pos")], [], (4, 5)),
    ("웨이팅 없이 바로 입장했고 음식도 빨리 나왔어요.", [("대기시간", "pos")], [], (4, 5)),
    ("단골 확정입니다. 맛도 서비스도 다 만족스러워요.", [("맛", "pos"), ("친절", "pos")], [], (5, 5)),
    ("인테리어가 감성적이라 사진 찍기 좋아요. 커피도 맛있고요.", [("분위기", "pos"), ("맛", "pos")], [], (4, 5)),
    ("직원분들이 세심하게 챙겨주셔서 좋았습니다.", [("친절", "pos")], [], (4, 5)),
]

NEU_TEMPLATES = [
    ("맛은 괜찮은데 특별하진 않아요. 무난합니다.", [("맛", "pos")], [], (3, 4)),
    ("평범한 동네 맛집 느낌. 나쁘지 않아요.", [], [], (3, 4)),
    ("양은 많은데 간이 조금 셌어요. 그래도 먹을만 합니다.", [("맛", "neg")], [], (3, 3)),
]

NEG_TEMPLATES = [
    ("웨이팅이 1시간 넘게 걸렸어요. 시간 아깝습니다.", [("대기시간", "neg")], ["웨이팅"], (2, 3)),
    ("직원이 불친절해서 기분이 상했습니다. 다신 안 갈 듯.", [("친절", "neg")], ["불친절"], (1, 2)),
    ("테이블이 끈적하고 위생이 별로였어요.", [("청결", "neg")], ["위생"], (1, 2)),
    ("가격이 갑자기 올랐네요. 양도 줄어든 느낌.", [("가격", "neg")], ["가격인상", "양"], (2, 3)),
    ("음식이 너무 짜고 식어서 나왔어요. 실망입니다.", [("맛", "neg")], ["짜다"], (1, 2)),
    ("주차할 곳이 없어서 한참 헤맸어요. 안내도 없고요.", [("기타", "neg")], ["주차"], (2, 3)),
    ("주문이 누락돼서 30분을 더 기다렸습니다. 사과도 없네요.", [("친절", "neg"), ("대기시간", "neg")], ["주문누락", "불친절"], (1, 1)),
    ("머리카락이 나왔어요. 위생 관리 좀 해주세요.", [("청결", "neg")], ["위생", "이물질"], (1, 1)),
]

REPLY_TEMPLATES = {
    "pos": "소중한 리뷰 감사합니다! 다음에 오실 때도 만족하실 수 있도록 늘 노력하겠습니다. :)",
    "neu": "방문해 주셔서 감사합니다. 말씀 주신 부분 참고해서 더 나아지는 모습 보여드리겠습니다.",
    "neg": "불편을 드려 정말 죄송합니다. 말씀 주신 내용은 바로 개선하겠습니다. 다시 기회를 주시면 좋은 모습으로 보답하겠습니다.",
}

STORES = [
    # (이름, 카테고리, 주소, 주간 리뷰수 범위, 긍정확률(시작→끝: 개선 추세))
    ("성수 브런치카페 온도", "카페", "서울 성동구 성수동 12-3", (5, 9), (0.55, 0.80)),
    ("망원 김치찜 온기", "한식", "서울 마포구 망원동 44-1", (4, 8), (0.70, 0.60)),
]
COMPETITORS = [
    # (이름, 카테고리, 연결할 내 매장 인덱스, 주간 리뷰수 범위, 긍정확률)
    ("성수 카페 클라우드", "카페", 0, (3, 6), (0.65, 0.65)),
    ("망원 김치찜 명가", "한식", 1, (3, 6), (0.72, 0.72)),
]

REPORTS = {
    0: (
        [
            {"level": "crit", "title": "주말 웨이팅 불만 급증", "evidence": "최근 4주 '대기시간' 부정 언급 다수, '웨이팅' 키워드 상위"},
            {"level": "warn", "title": "위생 관련 지적 반복", "evidence": "'청결' 부정 언급이 매주 발생"},
            {"level": "strength", "title": "맛 만족도는 상승세", "evidence": "'맛' 긍정 비중이 직전 기간보다 상승"},
            {"level": "opportunity", "title": "분위기 호평 → SNS 홍보 기회", "evidence": "'분위기' 긍정 언급과 사진 리뷰 비중 높음"},
        ],
        [
            {"title": "주말 예약제/대기 알림 도입", "detail": "네이버 예약 또는 테이블링으로 대기 스트레스 완화", "expected_effect": "대기시간 부정 리뷰 감소"},
            {"title": "마감 청소 체크리스트 운영", "detail": "테이블·바닥·화장실 일일 점검표 작성", "expected_effect": "청결 지적 재발 방지"},
            {"title": "포토존 해시태그 이벤트", "detail": "인스타 업로드 시 음료 사이즈업", "expected_effect": "신규 방문 유입 증가"},
        ],
    ),
    1: (
        [
            {"level": "crit", "title": "가격 인상 후 불만 증가", "evidence": "'가격' 부정 언급과 '가격인상' 키워드 급증"},
            {"level": "warn", "title": "긍정 비율 하락 추세", "evidence": "긍정 비율이 직전 기간 대비 하락"},
            {"level": "strength", "title": "단골 중심의 맛 호평 유지", "evidence": "'맛' 긍정 언급 비중 안정적"},
            {"level": "opportunity", "title": "점심 세트 수요 존재", "evidence": "'가격' 언급 리뷰에서 세트/구성 요구 반복"},
        ],
        [
            {"title": "점심 한정 세트 메뉴 출시", "detail": "김치찜+공기밥+음료 구성으로 체감 가격 방어", "expected_effect": "가격 불만 완화, 점심 회전율 상승"},
            {"title": "가격 인상 사유 안내문 게시", "detail": "원재료 가격 변동 안내로 납득도 제고", "expected_effect": "부정 리뷰 톤 완화"},
            {"title": "재방문 스탬프 쿠폰", "detail": "5회 방문 시 1인분 무료", "expected_effect": "단골 락인 강화"},
        ],
    ),
}


def _pick_template(sentiment: str):
    pool = {"pos": POS_TEMPLATES, "neu": NEU_TEMPLATES, "neg": NEG_TEMPLATES}[sentiment]
    return rng.choice(pool)


def _severity(sentiment: str, rating: int) -> tuple[str, bool]:
    if sentiment != "neg":
        return "normal", False
    if rating <= 1:
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


async def _seed_store_reviews(
    db, channel_id: int, weeks_cfg, pos_cfg, *, with_replies: bool
) -> list[tuple[Review, str, bool]]:
    """한 채널에 WEEKS 주 분량 리뷰+분석(+답글) 삽입. (리뷰, sentiment, urgent) 목록 반환."""
    lo, hi = weeks_cfg
    p_start, p_end = pos_cfg
    today = datetime.now(UTC).date()
    out = []
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
            body, aspects, keywords, (rlo, rhi) = _pick_template(sentiment)
            rating = rng.randint(rlo, rhi)
            written = week_monday + timedelta(days=rng.randint(0, 6))
            if written > today:
                written = today
            review = Review(
                channel_id=channel_id,
                dedup_key=f"seed-{channel_id}-{seq}",
                author_masked=rng.choice(AUTHORS),
                rating=rating,
                body=body,
                written_at=written,
            )
            db.add(review)
            await db.flush()

            severity, urgent = _severity(sentiment, rating)
            db.add(
                ReviewAnalysis(
                    review_id=review.id,
                    sentiment=sentiment,
                    severity=severity,
                    urgent=urgent,
                    aspects=[{"category": c, "polarity": p} for c, p in aspects],
                    keywords=keywords,
                    model_ver="seed-v1",
                    alerted_at=datetime.now(UTC) if urgent else None,
                )
            )

            # 내 매장 리뷰 70% 는 승인된 답글 보유 → 답변율이 살아있는 화면
            if with_replies and rng.random() < 0.7:
                db.add(
                    Reply(
                        review_id=review.id,
                        tone="apologetic" if sentiment == "neg" else "polite",
                        draft=REPLY_TEMPLATES[sentiment],
                        status="approved",
                        approved_at=datetime.now(UTC),
                    )
                )
            out.append((review, sentiment, urgent))
    return out


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

        for name, category, address, weeks_cfg, pos_cfg in STORES:
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
            rows = await _seed_store_reviews(db, channel.id, weeks_cfg, pos_cfg, with_replies=True)
            total_reviews += len(rows)

            # 긴급 리뷰 → alerts (최근 것 위주 2건)
            urgent_rows = [rv for rv, _, ug in rows if ug]
            for rv in urgent_rows[-2:]:
                db.add(
                    Alert(store_id=store.id, review_id=rv.id, kind="urgent_review", sent_via=["mock"])
                )
                total_urgent += 1

            my_stores.append(store)
            all_store_ids.append(store.id)

        for name, category, my_idx, weeks_cfg, pos_cfg in COMPETITORS:
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
            rows = await _seed_store_reviews(db, channel.id, weeks_cfg, pos_cfg, with_replies=False)
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
        print(f"데모 소유자(sub): {DEV_USER_ID}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
