"""T-07 완료 조건: generate()를 mock 한 단위 테스트.

실제 API 를 호출하지 않는다(BACKEND.md §11). 프롬프트 로딩·구조화 반환·재시도만 검증한다.
"""

from types import SimpleNamespace

import pytest

from app.llm import client
from app.llm.schemas import ReplyOut


# --------------------------- load_prompt ---------------------------
def test_load_prompt_real_file_and_substitution():
    text = client.load_prompt("reply_v1", review_body="맛있어요", tone="polite")
    assert "맛있어요" in text  # {review_body} 치환됨
    assert "{review_body}" not in text
    assert "가드레일" in text  # 가드레일 문구가 프롬프트 파일에 존재


def test_load_prompt_missing_raises():
    with pytest.raises(FileNotFoundError):
        client.load_prompt("존재하지않는프롬프트")


def test_load_prompt_preserves_unrelated_braces(tmp_path, monkeypatch):
    # JSON 예시({...})가 들어간 프롬프트를 str.format 이 깨뜨리지 않아야 한다
    p = tmp_path / "brace_test.md"
    p.write_text('예시 JSON: {"a": 1} / 변수: {name}', encoding="utf-8")
    monkeypatch.setattr(client, "_PROMPTS_DIR", tmp_path)
    out = client.load_prompt("brace_test", name="철수")
    assert '{"a": 1}' in out  # 무관한 중괄호 보존
    assert "철수" in out


# --------------------------- generate (mock) ---------------------------
def _fake_resp(parsed: object):
    return SimpleNamespace(
        parsed=parsed,
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=8),
    )


async def test_generate_returns_parsed_and_passes_schema(monkeypatch):
    captured = {}

    async def fake_generate_content(*, model, contents, config):
        captured["model"] = model
        captured["schema"] = config.response_schema
        captured["mime"] = config.response_mime_type
        return _fake_resp(ReplyOut(draft="감사합니다 고객님!"))

    monkeypatch.setattr(client._client.aio.models, "generate_content", fake_generate_content)

    out = await client.generate(
        "reply_v1",
        {"review_body": "맛있어요", "analysis": "", "tone": "polite", "tone_examples": ""},
        ReplyOut,
        model="gemini-2.0-flash",
    )
    assert isinstance(out, ReplyOut)
    assert out.draft == "감사합니다 고객님!"
    assert captured["model"] == "gemini-2.0-flash"
    assert captured["schema"] is ReplyOut
    assert captured["mime"] == "application/json"


async def test_generate_retries_once_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def flaky(*, model, contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("일시적 API 오류(429)")
        return _fake_resp(ReplyOut(draft="ok"))

    monkeypatch.setattr(client._client.aio.models, "generate_content", flaky)
    out = await client.generate("reply_v1", {"review_body": "x", "analysis": "",
                                             "tone": "polite", "tone_examples": ""}, ReplyOut)
    assert out.draft == "ok"
    assert calls["n"] == 2  # 최초 1 + 재시도 1


async def test_generate_reraises_after_retry_exhausted(monkeypatch):
    calls = {"n": 0}

    async def always_fail(*, model, contents, config):
        calls["n"] += 1
        raise RuntimeError("계속 실패")

    monkeypatch.setattr(client._client.aio.models, "generate_content", always_fail)
    with pytest.raises(RuntimeError, match="계속 실패"):
        await client.generate("reply_v1", {"review_body": "x", "analysis": "",
                                           "tone": "polite", "tone_examples": ""}, ReplyOut)
    assert calls["n"] == 2  # 2회 시도 후 포기


async def test_generate_none_parsed_triggers_retry(monkeypatch):
    calls = {"n": 0}

    async def none_then_ok(*, model, contents, config):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_resp(None)  # 파싱 실패 → 재시도
        return _fake_resp(ReplyOut(draft="recovered"))

    monkeypatch.setattr(client._client.aio.models, "generate_content", none_then_ok)
    out = await client.generate("reply_v1", {"review_body": "x", "analysis": "",
                                             "tone": "polite", "tone_examples": ""}, ReplyOut)
    assert out.draft == "recovered"
    assert calls["n"] == 2
