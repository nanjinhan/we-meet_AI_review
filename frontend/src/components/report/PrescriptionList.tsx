"use client";

import { Check, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Prescription } from "@/hooks/useReport";
import { cn } from "@/lib/utils";

/**
 * 처방 체크리스트. 체크 상태는 실행 여부 메모일 뿐이라 로컬에만 저장한다
 * (서버 스키마에 없는 값 — 백엔드 변경 없이 동작).
 */
export function PrescriptionList({
  items,
  reportId,
}: {
  items: Prescription[];
  reportId: number;
}) {
  const key = `wm.rx.${reportId}`;
  const [done, setDone] = useState<number[]>([]);

  useEffect(() => {
    try {
      setDone(JSON.parse(localStorage.getItem(key) ?? "[]"));
    } catch {
      setDone([]);
    }
  }, [key]);

  const toggle = (i: number) => {
    const next = done.includes(i) ? done.filter((d) => d !== i) : [...done, i];
    setDone(next);
    localStorage.setItem(key, JSON.stringify(next));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>이번 주 처방</CardTitle>
        <p className="text-xs text-muted-foreground">
          {done.length}/{items.length} 완료 — 체크는 이 기기에만 저장됩니다
        </p>
      </CardHeader>
      <CardContent className="space-y-2 pt-3">
        {items.map((rx, i) => {
          const checked = done.includes(i);
          return (
            <button
              key={i}
              onClick={() => toggle(i)}
              className={cn(
                "flex w-full items-start gap-3 rounded-lg border border-border p-3 text-left transition-colors hover:bg-muted",
                checked && "bg-muted",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                  checked
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card",
                )}
              >
                {checked && <Check className="h-3.5 w-3.5" />}
              </span>
              <span className="space-y-1">
                <span
                  className={cn(
                    "block text-sm font-medium",
                    checked && "text-muted-foreground line-through",
                  )}
                >
                  {rx.title}
                </span>
                <span className="block text-xs text-muted-foreground">{rx.detail}</span>
                <span className="inline-flex items-center gap-1 text-xs font-medium text-delta-up">
                  <TrendingUp className="h-3 w-3" />
                  {rx.expected_effect}
                </span>
              </span>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}
