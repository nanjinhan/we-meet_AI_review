"""유일한 LLM 게이트웨이 (Google Gemini).

CLAUDE.md 규칙 2: LLM 호출은 이 파일로만. 다른 모듈에서 google.genai 를 직접 import 금지.
프로바이더 교체 시 이 파일만 수정한다.

원 스펙은 Anthropic 기준이나 무료 티어 요구로 Gemini 로 구현했다(프로바이더 추상화 원칙).
스키마(schemas.py)·프롬프트(prompts/*.md)는 프로바이더와 무관하게 그대로 재사용된다.
(BACKEND.md §4, ARCHITECTURE.md §3-5)
"""

import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("llm")

_client = genai.Client(api_key=settings.gemini_api_key)

# backend/app/llm/client.py → parents[2] == backend/
_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str, /, **variables: object) -> str:
    """prompts/{name}.md 를 읽어 {var} 를 치환. 파일 없으면 즉시 에러.

    프롬프트 안의 JSON 예시({...})가 깨지지 않도록 str.format 이 아니라
    전달된 변수 키만 골라 치환한다. name 은 positional-only —
    변수 키가 'name' 이어도 충돌하지 않는다.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일 없음: {path}")
    text = path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _log_usage(prompt_name: str, model: str, resp: object) -> None:
    """호출·토큰 사용량을 JSON 로그로 남긴다(비용 추적)."""
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        logger.info(
            json.dumps(
                {
                    "event": "llm_call",
                    "prompt": prompt_name,
                    "model": model,
                    "input_tokens": getattr(usage, "prompt_token_count", None),
                    "output_tokens": getattr(usage, "candidates_token_count", None),
                },
                ensure_ascii=False,
            )
        )


async def generate(
    prompt_name: str,
    variables: dict,
    output_model: type[BaseModel],
    model: str | None = None,
    max_tokens: int = 4096,
) -> BaseModel:
    """structured outputs 로 스키마 보장. API 오류 시 1회 재시도 후 예외 전파.

    분류 호출은 model=settings.llm_model_classify, 생성은 기본값(llm_model_generate).
    """
    prompt = load_prompt(prompt_name, **variables)
    model = model or settings.llm_model_generate
    last_exc: Exception | None = None
    for attempt in range(2):  # 최초 + 1회 재시도
        try:
            resp = await _client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=output_model,
                    max_output_tokens=max_tokens,
                ),
            )
            _log_usage(prompt_name, model, resp)
            parsed = resp.parsed
            if parsed is None:
                raise ValueError("LLM 구조화 출력 파싱 실패")
            return parsed
        except Exception as exc:  # noqa: BLE001 - 재시도 목적상 광범위 캐치
            last_exc = exc
            logger.warning("LLM 호출 실패(attempt %d): %s", attempt + 1, exc)
    assert last_exc is not None
    raise last_exc


async def generate_stream(
    prompt_name: str,
    variables: dict,
    model: str | None = None,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """비서 최종 답변용 텍스트 스트리밍(스키마 없음). str 를 yield 하는 async generator."""
    prompt = load_prompt(prompt_name, **variables)
    model = model or settings.llm_model_generate
    stream = await _client.aio.models.generate_content_stream(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
