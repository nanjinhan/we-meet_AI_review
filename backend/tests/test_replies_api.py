"""T-09 완료 조건: generate→수정(재생성)→approve 왕복 API + 가드레일 문구가 프롬프트에 존재."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.llm import client as llm_client
from app.llm.schemas import ReplyOut
from app.pipeline.reply_gen import generate_reply
from tests.conftest import auth_headers


def _mock_llm(monkeypatch, draft="감사합니다 고객님! 더 나은 모습으로 보답하겠습니다."):
    async def fake_gc(*, model, contents, config):
        return SimpleNamespace(
            parsed=ReplyOut(draft=draft),
            usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
        )

    monkeypatch.setattr(llm_client._client.aio.models, "generate_content", fake_gc)


async def _seed_review(db, owner) -> tuple[int, int]:
    """store(owner) + settings + channel + review + analysis. (store_id, review_id) 반환."""
    store = models.Store(owner_id=owner, name="답글매장")
    db.add(store)
    await db.flush()
    db.add(models.StoreSettings(store_id=store.id, tone_examples=["항상 감사합니다 고객님!"]))
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    review = models.Review(
        channel_id=channel.id, dedup_key="r1", body="음식이 맛있어요",
        rating=5, written_at=date(2026, 6, 1),
    )
    db.add(review)
    await db.flush()
    db.add(
        models.ReviewAnalysis(
            review_id=review.id, sentiment="pos", severity="normal", urgent=False,
            aspects=[{"category": "맛", "polarity": "pos"}], keywords=["맛"],
            model_ver="gemini-2.0-flash",
        )
    )
    await db.flush()
    return store.id, review.id


# --------------------------- 가드레일 (완료 조건) ---------------------------
def test_reply_prompt_has_guardrails():
    text = (Path(__file__).resolve().parents[1] / "prompts" / "reply_v1.md").read_text(
        encoding="utf-8"
    )
    assert "약속" in text  # 보상·환불 약속 금지
    assert "법적" in text  # 법적 책임 인정 금지
    assert "150자" in text  # 분량 제한
    assert "인용" in text  # 고객 표현 그대로 인용 금지


# --------------------------- generate → 재생성(discard) → approve ---------------------------
async def test_reply_generate_regenerate_approve_roundtrip(client, db, monkeypatch):
    user = uuid4()
    h = auth_headers(user)
    _, review_id = await _seed_review(db, user)
    _mock_llm(monkeypatch, draft="첫 번째 초안입니다.")

    # 1) 생성
    res = await client.post(
        f"/api/v1/reviews/{review_id}/reply:generate", json={"tone": "polite"}, headers=h
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "draft"
    assert body["tone"] == "polite"
    assert body["draft"] == "첫 번째 초안입니다."
    first_id = body["id"]

    # 2) 재생성 → 기존 draft 는 discard, 새 draft 생성
    _mock_llm(monkeypatch, draft="두 번째(수정) 초안입니다.")
    res = await client.post(
        f"/api/v1/reviews/{review_id}/reply:generate", json={"tone": "friendly"}, headers=h
    )
    second = res.json()
    assert second["draft"] == "두 번째(수정) 초안입니다."
    assert second["id"] != first_id

    old = (await db.execute(select(models.Reply).where(models.Reply.id == first_id))).scalar_one()
    assert old.status == "discarded"  # 기존 초안 폐기됨

    # 3) 승인 → status='approved' + approved_at, draft 반환(클립보드 복사용)
    res = await client.post(f"/api/v1/replies/{second['id']}:approve", headers=h)
    assert res.status_code == 200
    approved = res.json()
    assert approved["status"] == "approved"
    assert approved["approved_at"] is not None
    assert approved["draft"] == "두 번째(수정) 초안입니다."


async def test_reply_ownership_404(client, db, monkeypatch):
    owner = uuid4()
    _, review_id = await _seed_review(db, owner)
    _mock_llm(monkeypatch)

    # 타 사용자는 생성 불가 → 404
    res = await client.post(
        f"/api/v1/reviews/{review_id}/reply:generate",
        json={"tone": "polite"},
        headers=auth_headers(uuid4()),
    )
    assert res.status_code == 404

    # 소유자가 생성한 답글을 타 사용자가 승인 시도 → 404
    reply = await generate_reply(db, review_id, "polite", generate_fn=_fake_gen("x"))
    await db.flush()
    res = await client.post(
        f"/api/v1/replies/{reply.id}:approve", headers=auth_headers(uuid4())
    )
    assert res.status_code == 404


# ---------------------- 검토 회귀: 경쟁매장 금지 / 폐기초안 승인 금지 ----------------------
async def test_competitor_review_reply_400(client, db, monkeypatch):
    """경쟁매장 채널 리뷰에는 답글 생성 금지 (TECH_SPEC §4.2)."""
    user = uuid4()
    store = models.Store(owner_id=user, name="경쟁보유매장")
    db.add(store)
    await db.flush()
    comp_channel = models.StoreChannel(store_id=store.id, platform="naver", is_competitor=True)
    db.add(comp_channel)
    await db.flush()
    review = models.Review(channel_id=comp_channel.id, dedup_key="c1", body="경쟁 리뷰")
    db.add(review)
    await db.flush()
    _mock_llm(monkeypatch)

    res = await client.post(
        f"/api/v1/reviews/{review.id}/reply:generate",
        json={"tone": "polite"},
        headers=auth_headers(user),
    )
    assert res.status_code == 400
    assert "경쟁매장" in res.json()["detail"]


async def test_discarded_reply_cannot_be_approved(client, db, monkeypatch):
    """재생성으로 폐기된 옛 초안은 승인 불가(409) — 승인은 최신 초안으로만."""
    user = uuid4()
    h = auth_headers(user)
    _, review_id = await _seed_review(db, user)

    _mock_llm(monkeypatch, draft="옛 초안")
    old_id = (
        await client.post(
            f"/api/v1/reviews/{review_id}/reply:generate", json={"tone": "polite"}, headers=h
        )
    ).json()["id"]

    _mock_llm(monkeypatch, draft="새 초안")
    await client.post(
        f"/api/v1/reviews/{review_id}/reply:generate", json={"tone": "polite"}, headers=h
    )

    # 폐기된 옛 초안 승인 시도 → 409
    res = await client.post(f"/api/v1/replies/{old_id}:approve", headers=h)
    assert res.status_code == 409

    old = (await db.execute(select(models.Reply).where(models.Reply.id == old_id))).scalar_one()
    assert old.status == "discarded"  # 상태 불변


# --------------------------- generate_reply 단위 (톤 프로필 few-shot) ---------------------------
def _fake_gen(draft: str, capture: dict | None = None):
    async def fake(prompt_name, variables, output_model):
        if capture is not None:
            capture.update(variables)
        return ReplyOut(draft=draft)

    return fake


async def test_generate_reply_passes_tone_profile(db):
    owner = uuid4()
    _, review_id = await _seed_review(db, owner)
    captured: dict = {}

    reply = await generate_reply(
        db, review_id, "apologetic", generate_fn=_fake_gen("초안", captured)
    )
    assert reply.tone == "apologetic"
    assert reply.status == "draft"
    # 사장님 톤 예시가 프롬프트 변수로 전달됨
    assert "항상 감사합니다 고객님!" in captured["tone_examples"]
    # 분석 요약도 전달됨
    assert "맛(pos)" in captured["analysis"]
