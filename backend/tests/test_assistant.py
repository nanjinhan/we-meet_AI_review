"""T-14 완료 조건: intent 3종(stats/evidence/both) E2E(mock LLM) + 데이터 0건 시 LLM 미호출.

라우터/답변 LLM 은 Gemini 호출(generate/generate_stream)을 monkeypatch 로 대체한다.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app import models
from app.llm import client as llm_client
from app.llm.schemas import RouterDecision
from app.pipeline.stats import week_start_of
from tests.conftest import auth_headers


def _mock_router(monkeypatch, decision: RouterDecision):
    async def fake_gc(*, model, contents, config):
        return SimpleNamespace(
            parsed=decision,
            usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
        )

    monkeypatch.setattr(llm_client._client.aio.models, "generate_content", fake_gc)


def _mock_answer(monkeypatch, tokens: list[str], calls: dict):
    async def fake_stream(*, model, contents, config):
        calls["n"] += 1

        async def gen():
            for t in tokens:
                yield SimpleNamespace(text=t)

        return gen()

    monkeypatch.setattr(llm_client._client.aio.models, "generate_content_stream", fake_stream)


def _cur_week():
    return week_start_of(datetime.now(UTC).date())


async def _store(db, owner, name="비서매장"):
    s = models.Store(owner_id=owner, name=name)
    db.add(s)
    await db.flush()
    return s


# --------------------------- stats ---------------------------
async def test_assistant_stats_intent(client, db, monkeypatch):
    owner = uuid4()
    h = auth_headers(owner)
    store = await _store(db, owner)
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=_cur_week(), aspect="대기시간",
                                    pos_cnt=1, neg_cnt=5, total_cnt=6, avg_rating=2.0))
    await db.flush()

    _mock_router(monkeypatch, RouterDecision(intent="stats", period_weeks=4))
    calls = {"n": 0}
    _mock_answer(monkeypatch, ["대기시간", " 문제가 가장 커요"], calls)

    res = await client.post(
        f"/api/v1/stores/{store.id}/assistant/messages",
        json={"message": "제일 큰 문제 뭐야?"}, headers=h,
    )
    assert res.status_code == 200
    assert "대기시간" in res.text
    assert "[DONE]" in res.text
    assert calls["n"] == 1  # 데이터 있음 → 답변 LLM 호출

    hist = (
        await client.get(f"/api/v1/stores/{store.id}/assistant/messages", headers=h)
    ).json()
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert "대기시간" in hist[1]["content"]


# --------------------------- evidence ---------------------------
async def test_assistant_evidence_intent(client, db, monkeypatch):
    owner = uuid4()
    h = auth_headers(owner)
    store = await _store(db, owner)
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    r = models.Review(channel_id=channel.id, dedup_key="e1", body="머리카락 나왔어요 위생 별로",
                      rating=1, written_at=datetime.now(UTC).date())
    db.add(r)
    await db.flush()
    db.add(models.ReviewAnalysis(review_id=r.id, sentiment="neg", severity="complaint",
                                 urgent=True, aspects=[], keywords=["위생"], model_ver="m"))
    await db.flush()

    _mock_router(monkeypatch, RouterDecision(intent="evidence", sentiment="neg",
                                             query_text="위생", period_weeks=4))
    calls = {"n": 0}
    _mock_answer(monkeypatch, ["위생 관련 리뷰가 있어요"], calls)

    res = await client.post(
        f"/api/v1/stores/{store.id}/assistant/messages",
        json={"message": "위생 리뷰 보여줘"}, headers=h,
    )
    assert res.status_code == 200
    assert calls["n"] == 1  # 폴백 근거검색으로 리뷰 발견 → 답변 LLM 호출
    assert "위생" in res.text


# --------------------------- both ---------------------------
async def test_assistant_both_intent(client, db, monkeypatch):
    owner = uuid4()
    h = auth_headers(owner)
    store = await _store(db, owner)
    db.add(models.WeeklyAspectStats(store_id=store.id, week_start=_cur_week(), aspect="대기시간",
                                    pos_cnt=1, neg_cnt=4, total_cnt=5, avg_rating=2.0))
    channel = models.StoreChannel(store_id=store.id, platform="csv")
    db.add(channel)
    await db.flush()
    r = models.Review(channel_id=channel.id, dedup_key="b1", body="대기가 너무 길어요",
                      rating=2, written_at=datetime.now(UTC).date())
    db.add(r)
    await db.flush()
    db.add(models.ReviewAnalysis(
        review_id=r.id, sentiment="neg", severity="uncomfortable", urgent=False,
        aspects=[{"category": "대기시간", "polarity": "neg"}], keywords=["대기"], model_ver="m",
    ))
    await db.flush()

    _mock_router(monkeypatch, RouterDecision(intent="both", aspect="대기시간", period_weeks=4))
    calls = {"n": 0}
    _mock_answer(monkeypatch, ["대기시간 통계와 리뷰 요약입니다"], calls)

    res = await client.post(
        f"/api/v1/stores/{store.id}/assistant/messages",
        json={"message": "대기시간 어때? 관련 리뷰도"}, headers=h,
    )
    assert res.status_code == 200
    assert calls["n"] == 1
    assert "대기시간" in res.text


# --------------------------- 데이터 0건 → 답변 LLM 미호출 ---------------------------
async def test_assistant_no_data_skips_answer_llm(client, db, monkeypatch):
    owner = uuid4()
    h = auth_headers(owner)
    store = await _store(db, owner, name="빈매장")  # 통계·리뷰 없음

    _mock_router(monkeypatch, RouterDecision(intent="stats", period_weeks=4))
    calls = {"n": 0}
    _mock_answer(monkeypatch, ["이건 호출되면 안 됨"], calls)

    res = await client.post(
        f"/api/v1/stores/{store.id}/assistant/messages",
        json={"message": "문제 뭐야?"}, headers=h,
    )
    assert res.status_code == 200
    assert "데이터가 부족" in res.text
    assert calls["n"] == 0  # 답변 LLM 미호출 (환각 방지)

    # 소유권: 타 사용자 404
    assert (
        await client.post(
            f"/api/v1/stores/{store.id}/assistant/messages",
            json={"message": "x"}, headers=auth_headers(uuid4()),
        )
    ).status_code == 404
