import { createBrowserClient } from "@supabase/ssr";

/** Supabase 환경변수가 설정됐는지 (미설정 시 개발 스캐폴딩 모드로 동작). */
export function isSupabaseConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  );
}

/** 브라우저용 Supabase 클라이언트 (Auth 용도로만 사용 — 데이터는 FastAPI 경유). */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
