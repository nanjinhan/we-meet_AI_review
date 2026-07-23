import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 모든 백엔드 호출의 단일 통로. Supabase 세션 토큰을 Bearer 로 붙이고,
 * 401 이면 refreshSession 1회 후 재시도한다. 컴포넌트에서 fetch 직접 호출 금지.
 * (FRONTEND.md §3)
 */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const configured = isSupabaseConfigured();
  const supabase = configured ? createClient() : null;

  const send = (token?: string) =>
    fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });

  let token: string | undefined;
  if (supabase) {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    token = session?.access_token;
  }

  let res = await send(token);

  if (res.status === 401 && supabase) {
    const { data } = await supabase.auth.refreshSession();
    if (data.session) {
      res = await send(data.session.access_token);
    } else if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  if (res.status === 204) return undefined as T;
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}
