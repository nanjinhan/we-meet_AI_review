/**
 * 웹푸시 구독 등록 (T-F6, FRONTEND.md §6).
 *
 * 흐름: 권한 요청 → SW의 PushManager로 구독 → `POST /push/subscribe`(backend/app/routers/auth.py).
 * VAPID 공개키가 없으면(.env 미설정) 구독을 시도하지 않고 "no-vapid-key"를 반환한다 —
 * 백엔드도 같은 이유로 발송을 skip(0)하므로(notify/webpush.py) 조용히 맞춰준다.
 */

import { api } from "@/lib/api";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;

export type PushSubscribeOutcome =
  | "subscribed"
  | "denied"
  | "unsupported"
  | "no-vapid-key";

/** iOS Safari는 홈 화면에 설치(standalone)된 상태에서만 Notification API를 노출한다. */
export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** base64url(VAPID 공개키) → Uint8Array (PushManager.subscribe가 요구하는 형태). */
function urlBase64ToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  // ArrayBuffer로 명시 할당 — lib.dom 최신 타입은 applicationServerKey에 SharedArrayBuffer 기반
  // Uint8Array(ArrayBufferLike)를 허용하지 않는다.
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** 현재 구독 여부(이미 권한을 받고 구독까지 돼 있는지)를 조회한다. UI 초기 상태용. */
export async function getExistingSubscription(): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return null;
  return reg.pushManager.getSubscription();
}

/**
 * 알림 권한 요청 → 구독 → 서버 저장까지 한 번에 수행한다.
 * 반드시 버튼 클릭 등 사용자 제스처 안에서 호출할 것(브라우저가 제스처 없는 권한 요청을 막는다).
 */
export async function subscribeToPush(): Promise<PushSubscribeOutcome> {
  if (!isPushSupported()) return "unsupported";
  if (!VAPID_PUBLIC_KEY) return "no-vapid-key";

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";

  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    }));

  const json = subscription.toJSON() as { endpoint: string; keys?: { p256dh: string; auth: string } };
  if (!json.keys) throw new Error("PushSubscription에 keys가 없습니다.");

  await api("/push/subscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  });

  return "subscribed";
}

/** 알림 끄기 — 브라우저 구독을 해지한다(서버 쪽 레코드는 다음 발송 시 410 Gone으로 정리됨). */
export async function unsubscribeFromPush(): Promise<void> {
  const sub = await getExistingSubscription();
  await sub?.unsubscribe();
}
