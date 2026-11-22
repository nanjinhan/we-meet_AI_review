"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { SufficiencyBadge } from "@/components/insights/SufficiencyBadge";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Card, CardContent } from "@/components/ui/card";
import type { Dashboard } from "@/hooks/useDashboard";
import { fmtPeriod } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

/**
 * 종합 평판 점수 + 자료 충분도.
 * 점수(만족도)와 '그 점수를 뒷받침하는 리뷰가 얼마나 있는지'는 다른 질문이라 따로 보여준다.
 */
export function ScoreCard({ data }: { data: Dashboard }) {
  const { score, score_delta: delta } = data;
  const up = (delta ?? 0) >= 0;
  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
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
        </div>

        {/* 자료 충분도 — 점수가 아니라 점수 옆에 붙는 주석 */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 border-t border-border pt-3">
          <SufficiencyBadge level={data.sufficiency} />
          <span className="tnum text-xs text-muted-foreground">
            {fmtPeriod(data.period_start, data.period_end)} · 분석 리뷰{" "}
            {data.total_reviews.toLocaleString("ko-KR")}건 기준
          </span>
          {data.sufficiency === "low" && (
            <span className="text-xs text-amber-700">
              리뷰가 더 쌓이기 전까지 점수는 참고용으로만 보세요.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
