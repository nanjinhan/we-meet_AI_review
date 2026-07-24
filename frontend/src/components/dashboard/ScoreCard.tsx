"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function ScoreCard({ score, delta }: { score: number; delta: number | null }) {
  const up = (delta ?? 0) >= 0;
  return (
    <Card>
      <CardContent className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-muted-foreground">종합 평판 점수</p>
          <div className="mt-1.5 flex items-end gap-3">
            <span className="tnum text-5xl font-semibold tracking-tight">
              <AnimatedNumber value={score} precision={1} />
            </span>
            <span className="mb-1.5 text-sm text-subtle-foreground">/ 100</span>
            {delta != null && (
              <span
                className={cn(
                  "tnum mb-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
                  up ? "bg-delta-up/10 text-delta-up" : "bg-delta-down/10 text-delta-down",
                )}
              >
                {up ? (
                  <TrendingUp className="h-3.5 w-3.5" />
                ) : (
                  <TrendingDown className="h-3.5 w-3.5" />
                )}
                {up ? "+" : ""}
                {delta.toFixed(1)}
              </span>
            )}
          </div>
          <p className="mt-2 text-xs text-subtle-foreground">직전 동일 기간 대비</p>
        </div>
        {/* 점수 게이지 — 숫자를 시각적으로 한 번 더 (0~100) */}
        <div className="w-full max-w-56">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-700"
              style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
            />
          </div>
          <div className="tnum mt-1 flex justify-between text-[10px] text-subtle-foreground">
            <span>0</span>
            <span>50</span>
            <span>100</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
