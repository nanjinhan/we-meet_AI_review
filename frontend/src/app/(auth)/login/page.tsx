"use client";

import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export default function LoginPage() {
  const [msg, setMsg] = useState<string | null>(null);

  const loginKakao = async () => {
    if (!isSupabaseConfigured()) {
      setMsg("아직 Supabase 미설정 (스캐폴딩 단계). 키를 넣으면 카카오 로그인이 켜집니다.");
      return;
    }
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "kakao",
      options: { redirectTo: `${location.origin}/dashboard` },
    });
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col items-center gap-6 py-10">
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Sparkles className="h-6 w-6" />
            </span>
            <div>
              <h1 className="text-2xl font-bold">리뷰 진단 AI</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                네이버 플레이스 리뷰 분석 · AI 답글 · 리포트
              </p>
            </div>
          </div>

          <button
            onClick={loginKakao}
            className="w-full rounded-lg bg-[#FEE500] px-4 py-3 font-medium text-[#191600] transition hover:brightness-95"
          >
            카카오로 시작하기
          </button>

          {msg && <p className="max-w-xs text-center text-xs text-amber-600">{msg}</p>}

          {!isSupabaseConfigured() && (
            <p className="text-center text-xs text-subtle-foreground">
              개발 모드: 인증 없이 화면을 둘러볼 수 있습니다 (예: /dashboard)
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
