"""애플리케이션 설정 — 모든 env 로딩의 단일 창구.

다른 모듈에서 os.environ 직접 접근 금지. 반드시 `from app.config import settings` 로 접근.
(BACKEND.md §1)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- 필수 ---
    database_url: str  # postgresql+asyncpg://... (Supabase session pooler 5432)
    supabase_jwt_secret: str
    gemini_api_key: str  # Google Gemini (무료 티어). LLM 게이트웨이 llm/client.py 에서만 사용
    internal_api_key: str  # /internal/* 보호용

    # --- LLM 모델 (env 오버라이드 가능) ---
    # 원 스펙은 Anthropic(Haiku/Sonnet) 기준이나, 무료 티어 요구로 Gemini 로 구현.
    # 프로바이더 교체는 llm/client.py 한 파일만 수정하면 된다(CLAUDE.md 규칙 2).
    llm_model_classify: str = "gemini-2.0-flash"  # 분류: 대량·단순
    llm_model_generate: str = "gemini-2.5-flash"  # 생성: 답글·리포트·비서

    # --- 카카오 (P3에서 사용) ---
    kakao_rest_api_key: str = ""
    kakao_redirect_uri: str = ""

    # --- 웹푸시 VAPID (P3에서 사용) ---
    vapid_public_key: str = ""
    vapid_private_key: str = ""

    # --- 크롤러 스냅샷 ---
    snapshot_dir: str = "/data/snapshots"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
