"use client";

import { EyeOff } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useSetExclusion } from "@/hooks/useInsights";
import { EXCLUDE_REASONS } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

/**
 * 리뷰 한 건을 '분석에서 제외'하는 컨트롤. 반드시 이유를 고르거나 적어야 한다.
 * 시스템이 대신 눌러 주는 경로는 없다 — 제외는 항상 사람이 결정하고, 내역에 이유가 남는다.
 */
export function ExcludeControl({ reviewId }: { reviewId: number }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(EXCLUDE_REASONS[0]);
  const [custom, setCustom] = useState("");
  const mutation = useSetExclusion();

  const finalReason = (custom.trim() || reason).slice(0, 200);

  if (!open) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <EyeOff className="h-3 w-3" />
        분석에서 제외
      </button>
    );
  }

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className="w-full space-y-2 rounded-lg border border-border bg-muted/60 p-2.5"
    >
      <p className="text-[11px] font-medium text-muted-foreground">
        제외 이유 (제외 내역에 그대로 남습니다)
      </p>
      <div className="flex flex-wrap gap-1.5">
        {EXCLUDE_REASONS.map((r) => (
          <button
            key={r}
            onClick={() => {
              setReason(r);
              setCustom("");
            }}
            className={cn(
              "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
              !custom.trim() && reason === r
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-card text-muted-foreground hover:bg-muted",
            )}
          >
            {r}
          </button>
        ))}
      </div>
      <input
        value={custom}
        onChange={(e) => setCustom(e.target.value)}
        maxLength={200}
        placeholder="다른 이유 직접 입력"
        className="w-full rounded-md border border-input bg-card px-2.5 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {mutation.isError && (
        <p className="text-[11px] text-destructive">제외하지 못했습니다. 다시 시도해 주세요.</p>
      )}
      <div className="flex justify-end gap-1.5">
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          취소
        </Button>
        <Button
          size="sm"
          disabled={mutation.isPending || !finalReason}
          onClick={() => mutation.mutate({ reviewId, excluded: true, reason: finalReason })}
        >
          {mutation.isPending ? "처리 중…" : "제외하기"}
        </Button>
      </div>
    </div>
  );
}
