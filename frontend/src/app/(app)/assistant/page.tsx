"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Sparkles } from "lucide-react";
import { useState } from "react";
import { ChatInput } from "@/components/assistant/ChatInput";
import { ChatMessages, type ChatItem } from "@/components/assistant/ChatMessages";
import { useStore } from "@/components/store-provider";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { sseStream } from "@/lib/sse";

type ChatMessageOut = components["schemas"]["ChatMessageOut"];

const SUGGESTIONS = [
  "최근 4주 동안 우리 가게 문제가 뭐야?",
  "웨이팅 관련 부정 리뷰 보여줘",
  "친절 항목은 요즘 어때?",
  "지난달이랑 비교해서 나아졌어?",
];

export default function AssistantPage() {
  const { store, isLoading: storeLoading } = useStore();

  // 서버 히스토리는 최초 1회만 — 이후 대화는 로컬 state 로 이어붙인다.
  const { data: history, isLoading } = useQuery({
    queryKey: ["assistant-history", store?.id],
    queryFn: () => api<ChatMessageOut[]>(`/stores/${store?.id}/assistant/messages`),
    enabled: store?.id != null,
    staleTime: Infinity,
  });

  const [session, setSession] = useState<ChatItem[]>([]);
  const [streaming, setStreaming] = useState(false);

  const items: ChatItem[] = [
    ...(history ?? []).map((m) => ({
      role: (m.role === "user" ? "user" : "assistant") as ChatItem["role"],
      content: m.content,
    })),
    ...session,
  ];

  const send = async (message: string) => {
    if (!store) return;
    setStreaming(true);
    // 사용자 메시지 + 빈 어시스턴트 버블을 먼저 그리고, 토큰이 올 때마다 채운다
    setSession((prev) => [
      ...prev,
      { role: "user", content: message },
      { role: "assistant", content: "", streaming: true },
    ]);

    try {
      for await (const token of sseStream(`/stores/${store.id}/assistant/messages`, {
        message,
      })) {
        setSession((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + token };
          return next;
        });
      }
    } catch {
      setSession((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...last,
          content: last.content || "응답을 받지 못했어요. 백엔드가 실행 중인지 확인해 주세요.",
        };
        return next;
      });
    } finally {
      setSession((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, streaming: false };
        return next;
      });
      setStreaming(false);
    }
  };

  const empty = !isLoading && items.length === 0;

  return (
    <section className="flex min-h-[calc(100vh-12rem)] flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold">AI 비서</h1>
        <p className="text-sm text-muted-foreground">
          {store ? `${store.name}의 리뷰 데이터를 근거로 답합니다` : "매장 데이터 기반 질의응답"}
        </p>
      </div>

      <div className="flex-1">
        {(storeLoading || isLoading) && (
          <div className="space-y-3">
            <Skeleton className="h-14 w-2/3" />
            <Skeleton className="ml-auto h-10 w-1/2" />
            <Skeleton className="h-14 w-3/4" />
          </div>
        )}

        {empty && (
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                <Bot className="h-6 w-6" />
              </span>
              <div>
                <p className="text-sm font-medium">무엇이든 물어보세요</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  리뷰 통계와 실제 리뷰를 근거로 답하고, 데이터가 없으면 없다고 말합니다.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    disabled={streaming || !store}
                    className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
                  >
                    <Sparkles className="h-3 w-3" />
                    {q}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {items.length > 0 && <ChatMessages items={items} />}
      </div>

      <div className="sticky bottom-16 md:bottom-2">
        <ChatInput onSend={send} disabled={streaming || !store} />
      </div>
    </section>
  );
}
