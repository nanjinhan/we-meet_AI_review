"use client";

import { Share, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";

const DISMISS_KEY = "wm.installBannerDismissed";

/** 사용자 에이전트로 iOS(아이폰/아이패드) Safari 여부를 판별한다. iPadOS 13+는 데스크톱 UA를 쓰므로 터치포인트로 보강. */
function detectIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const isIPhoneLike = /iPad|iPhone|iPod/.test(ua);
  const isIPadOS13Plus = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return isIPhoneLike || isIPadOS13Plus;
}

function detectStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
}

/**
 * iOS 설치 안내 배너 (T-F6).
 * iOS Safari는 PWA로 "홈 화면에 추가"한 뒤에만 웹푸시(Notification API)를 허용한다 —
 * 그 전까지는 `lib/push.ts`의 구독 요청이 조용히 실패하므로, 구독을 유도하는 화면(온보딩 알림 스텝 등)에
 * 먼저 이 배너로 설치 경로를 안내한다. 닫으면 localStorage에 기억해 다시 보여주지 않는다.
 */
export function InstallBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      // 프라이빗 모드 등으로 localStorage 접근 불가 — 배너는 그냥 보여준다
    }
    if (detectIOS() && !detectStandalone()) setVisible(true);
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    setVisible(false);
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // 저장 실패해도 이번 세션에서는 이미 닫힌 상태
    }
  };

  return (
    <Card className="border-primary/30 bg-accent">
      <CardContent className="flex items-start gap-3 py-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Share className="h-4.5 w-4.5" />
        </span>
        <div className="flex-1 text-sm">
          <p className="font-medium text-accent-foreground">홈 화면에 추가하면 알림을 받을 수 있어요</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            iPhone·iPad에서는 먼저 Safari 하단의 공유 버튼(<Share className="inline h-3 w-3" />)을 누른 뒤{" "}
            <strong className="text-foreground">&lsquo;홈 화면에 추가&rsquo;</strong>를 선택해 주세요. 설치 후 다시 들어오면
            알림을 켤 수 있어요.
          </p>
        </div>
        <button
          onClick={dismiss}
          aria-label="배너 닫기"
          className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted"
        >
          <X className="h-4 w-4" />
        </button>
      </CardContent>
    </Card>
  );
}
