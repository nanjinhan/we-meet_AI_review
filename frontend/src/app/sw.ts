/**
 * 서비스워커 소스 — @serwist/next 가 번들링해 public/sw.js 로 뽑아낸다 (T-F6).
 * 역할은 설치 가능성(manifest) + 웹푸시 수신뿐. 오프라인 캐싱 전략은 Serwist 기본값만 쓴다
 * (FRONTEND.md §1 "오프라인은 불필요"). push/notificationclick 핸들러만 직접 구현.
 */

import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { Serwist } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: defaultCache,
});

serwist.addEventListeners();

/** 백엔드 webpush.py가 보내는 페이로드 형태 (FRONTEND.md §6). */
interface PushPayload {
  title: string;
  body: string;
  url?: string;
}

self.addEventListener("push", (event) => {
  let payload: PushPayload = { title: "리뷰 진단 AI", body: "새 알림이 있어요." };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    // 페이로드가 JSON이 아니면 기본 문구로 대체
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: payload.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string } | undefined)?.url || "/";

  event.waitUntil(
    (async () => {
      const clientsList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const existing = clientsList.find((c) => new URL(c.url).pathname === new URL(url, self.location.origin).pathname);
      if (existing) {
        await existing.focus();
        return;
      }
      await self.clients.openWindow(url);
    })(),
  );
});
