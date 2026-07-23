"use client";

import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { useState } from "react";

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
      <div className="text-center">
        <h1 className="text-2xl font-bold">리뷰 진단 AI</h1>
        <p className="mt-2 text-sm text-gray-500">소상공인 리뷰 분석·답글·리포트</p>
      </div>

      <button
        onClick={loginKakao}
        className="w-64 rounded-lg bg-[#FEE500] px-4 py-3 font-medium text-[#191600] hover:brightness-95"
      >
        카카오로 시작하기
      </button>

      {msg && <p className="max-w-xs text-center text-xs text-amber-600">{msg}</p>}

      {!isSupabaseConfigured() && (
        <p className="text-xs text-gray-400">
          개발 모드: 인증 없이 화면을 둘러볼 수 있습니다 (예: /dashboard)
        </p>
      )}
    </main>
  );
}
