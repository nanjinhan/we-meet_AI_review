import { API_BASE, ApiError, getToken } from "@/lib/api";

/**
 * fetch 기반 SSE 소비 (FRONTEND.md §5).
 * EventSource 는 Authorization 헤더를 못 붙이므로 POST + ReadableStream 으로 파싱한다.
 * "data: " 프레임 단위로 yield 하고 "[DONE]" 에서 종료한다.
 */
export async function* sseStream(path: string, body: unknown): AsyncGenerator<string> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, await res.text());
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") return;
          yield data;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
