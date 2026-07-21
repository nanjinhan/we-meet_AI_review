"""카카오 연동 / 웹푸시 구독 DTO."""

from pydantic import BaseModel


class KakaoCallbackResult(BaseModel):
    connected: bool


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeIn(BaseModel):
    # 브라우저 PushSubscription.toJSON() 형태
    endpoint: str
    keys: PushKeys


class PushSubscribeResult(BaseModel):
    ok: bool
