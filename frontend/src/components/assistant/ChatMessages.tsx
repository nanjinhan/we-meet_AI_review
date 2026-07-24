"use client";

import { Bot } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

export type ChatItem = {
  role: "user" | "assistant";
  content: string;
  /** 스트리밍 중인 마지막 어시스턴트 메시지 표시용 */
  streaming?: boolean;
};

export function ChatMessages({ items }: { items: ChatItem[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  // 새 토큰이 붙을 때마다 맨 아래로
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items]);

  return (
    <div className="space-y-3">
      {items.map((m, i) => (
        <div
          key={i}
          className={cn("flex items-end gap-2", m.role === "user" && "justify-end")}
        >
          {m.role === "assistant" && (
            <span className="mb-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Bot className="h-4 w-4" />
            </span>
          )}
          <div
            className={cn(
              "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
              m.role === "user"
                ? "rounded-br-md bg-primary text-primary-foreground"
                : "rounded-bl-md border border-border bg-card",
            )}
          >
            {m.content}
            {m.streaming && (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-muted-foreground align-text-bottom" />
            )}
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
