"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function ScoreCard({ score, delta }: { score: number; delta: number | null }) {
  const up = (delta ?? 0) >= 0;
  return (
    <Card className="relative overflow-hidden">
      {/* cult-ui 풍 그라데이션 하이라이트 */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-accent/70 to-transparent" />
      <CardContent className="relative">
        <p className="text-xs font-medium text-muted-foreground">종합 평판 점수</p>
        <div className="mt-1 flex items-end gap-3">
          <span className="text-5xl font-bold tracking-tight">
            <AnimatedNumber value={score} precision={1} />
          </span>
          <span className="mb-1.5 text-sm text-subtle-foreground">/ 100</span>
          {delta != null && (
            <span
              className={cn(
                "mb-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
                up ? "bg-delta-up/10 text-delta-up" : "bg-delta-down/10 text-delta-down",
              )}
            >
              {up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {up ? "+" : ""}
              {delta.toFixed(1)}
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-subtle-foreground">직전 동일 기간 대비</p>
      </CardContent>
    </Card>
  );
}
