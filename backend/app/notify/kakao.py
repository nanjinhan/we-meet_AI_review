"""카카오 "나에게 보내기" 발송 + 토큰 관리.

kakao_tokens 에서 토큰 로드, 만료 시 refresh_token 으로 갱신 후 저장. 온보딩(/auth/kakao/callback)
에서 최초 저장. 실제 발송은 kapi 메모 API. KAKAO_REST_API_KEY 미설정 시 안전하게 skip(False).
(BACKEND.md §7, TECH_SPEC §6)
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.config import settings
from app.models import KakaoToken

logger = logging.getLogger("notify.kakao")

KAUTH_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
_DEFAULT_EXPIRES = 21600  # 6h

# 테스트에서 httpx.MockTransport 를 주입한다(라이브 호출 금지).
_transport: httpx.AsyncBaseTransport | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_transport, timeout=10.0)


async def _refresh(db, token: KakaoToken) -> bool:
    """refresh_token 으로 access_token 갱신 후 저장. 성공 여부."""
    async with _client() as c:
        resp = await c.post(
            KAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.kakao_rest_api_key,
                "refresh_token": token.refresh_token,
            },
        )
    if resp.status_code != 200:
        logger.warning("카카오 토큰 갱신 실패: %s", resp.status_code)
        return False
    data = resp.json()
    token.access_token = data["access_token"]
    token.expires_at = _now() + timedelta(seconds=data.get("expires_in", _DEFAULT_EXPIRES))
    if data.get("refresh_token"):  # 카카오는 갱신 시 새 refresh_token 을 줄 수 있다
        token.refresh_token = data["refresh_token"]
    token.updated_at = _now()
    return True


async def send_memo(db, user_id, text: str, url: str | None = None) -> bool:
    """사용자의 카카오톡으로 '나에게 보내기'. 성공 여부. 키/토큰 없으면 False."""
    if not settings.kakao_rest_api_key:
        return False
    token = await db.get(KakaoToken, user_id)
    if token is None:
        return False
    if _now() >= token.expires_at and not await _refresh(db, token):
        return False

    template = {
        "object_type": "text",
        "text": text[:1000],
        "link": {"web_url": url or "", "mobile_web_url": url or ""},
    }
    payload = {"template_object": json.dumps(template, ensure_ascii=False)}

    async with _client() as c:
        resp = await c.post(
            MEMO_SEND_URL,
            headers={"Authorization": f"Bearer {token.access_token}"},
            data=payload,
        )
        if resp.status_code == 401 and await _refresh(db, token):
            resp = await c.post(
                MEMO_SEND_URL,
                headers={"Authorization": f"Bearer {token.access_token}"},
                data=payload,
            )
    if resp.status_code != 200:
        logger.warning("카카오 발송 실패: %s", resp.status_code)
        return False
    return True


async def exchange_code(db, user_id, code: str) -> bool:
    """인가 코드 → 토큰 교환 후 kakao_tokens 저장(최초 연동). 성공 여부."""
    if not settings.kakao_rest_api_key:
        return False
    async with _client() as c:
        resp = await c.post(
            KAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.kakao_rest_api_key,
                "redirect_uri": settings.kakao_redirect_uri,
                "code": code,
            },
        )
    if resp.status_code != 200:
        logger.warning("카카오 코드 교환 실패: %s", resp.status_code)
        return False
    data = resp.json()
    expires_at = _now() + timedelta(seconds=data.get("expires_in", _DEFAULT_EXPIRES))
    token = await db.get(KakaoToken, user_id)
    if token is None:
        db.add(
            KakaoToken(
                user_id=user_id,
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                expires_at=expires_at,
            )
        )
    else:
        token.access_token = data["access_token"]
        if data.get("refresh_token"):
            token.refresh_token = data["refresh_token"]
        token.expires_at = expires_at
        token.updated_at = _now()
    return True
