"""웹푸시(VAPID) 발송.

push_subscriptions 의 사용자 기기 전체에 발송. 410 Gone 이면 만료된 구독으로 보고 삭제.
VAPID 키 미설정 시 안전하게 skip(0). pywebpush 는 동기라 스레드로 넘긴다.
(BACKEND.md §7)
"""

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import PushSubscription

logger = logging.getLogger("notify.webpush")


def _do_send(subscription_info: dict, data: str) -> None:
    """실제 pywebpush 호출(동기). 테스트에서 이 함수를 monkeypatch 한다."""
    from pywebpush import webpush  # 지연 import — 미설치 환경에서도 모듈 로드 가능

    webpush(
        subscription_info=subscription_info,
        data=data,
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": "mailto:admin@wemeet.example"},
    )


async def send_webpush(
    db: AsyncSession, user_id, title: str, body: str, url: str | None = None
) -> int:
    """사용자의 모든 구독 기기에 발송. 성공 발송 수 반환. 410 구독은 삭제."""
    if not settings.vapid_private_key:
        return 0
    subs = (
        await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()
    if not subs:
        return 0

    data = json.dumps({"title": title, "body": body, "url": url or "/"}, ensure_ascii=False)
    sent = 0
    for sub in subs:
        info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
        try:
            await asyncio.to_thread(_do_send, info, data)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - 개별 기기 실패는 전체를 막지 않는다
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 410:
                await db.delete(sub)  # Gone — 만료된 구독 정리
                logger.info("만료 구독 삭제: %s", sub.endpoint[:40])
            else:
                logger.warning("웹푸시 발송 실패: %s", exc)
    return sent
