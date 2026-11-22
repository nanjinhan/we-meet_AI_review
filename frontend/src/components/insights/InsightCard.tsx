"use client";

import { ChevronRight, ListChecks, Quote } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { InsightItem } from "@/hooks/useInsights";
import { fmtDay, POLARITY_LABEL } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

/**
 * 항목 하나의 근거 요약 카드 — "분석 리뷰 N건 중 M건"을 가장 크게, 그 아래 반복 정도·직전 기간·
 * 근거 문장을 붙인다. 카드 전체가 '근거 리뷰 보기' 버튼이다.
 */
export function InsightCard({
  item,
  minRelated,
  activeActions,
  onOpen,
}: {
  item: InsightItem;
  minRelated: number;
  /** 이 항목에 진행 중인 실행 과제 수 */
  activeActions: number;
  onOpen: () => void;
}) {
  const neg = item.polarity === "neg";
  const share = item.analyzed_cnt ? (item.related_cnt / item.analyzed_cnt) * 100 : 0;

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}
      className="cursor-pointer transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <p className="truncate text-sm font-semibold">{item.aspect}</p>
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                neg ? "bg-chart-neg/10 text-chart-neg" : "bg-chart-pos/10 text-chart-pos",
              )}
            >
              {POLARITY_LABEL[item.polarity]}
            </span>
          </div>
          <p className="tnum shrink-0 text-right text-sm text-muted-foreground">
            {item.analyzed_cnt}건 중{" "}
            <span className="text-2xl font-semibold tracking-tight text-foreground">
              {item.related_cnt}
            </span>
            건
          </p>
        </div>

        {/* 분모 대비 길이 — 숫자를 한 번 더 눈으로 */}
        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full", neg ? "bg-chart-neg" : "bg-chart-pos")}
            style={{ width: `${Math.max(2, Math.min(100, share))}%` }}
          />
        </div>

        <p className="tnum text-xs text-muted-foreground">
          {item.range_weeks}주 중 {item.weeks_mentioned}주에서 언급 · 최근 {fmtDay(item.last_written_at)}
          {" · "}
          {item.prev_analyzed_cnt > 0
            ? `직전 ${item.range_weeks}주 ${item.prev_analyzed_cnt}건 중 ${item.prev_related_cnt}건`
            : "직전 기간 자료 없음"}
        </p>

        {!item.enough && (
          <p className="rounded-md bg-level-warn/10 px-2.5 py-1.5 text-[11px] text-amber-700">
            관련 리뷰가 {minRelated}건 미만이라 ‘반복’이라고 말하기에는 이릅니다.
          </p>
        )}

        {item.quotes.length > 0 && (
          <ul className="space-y-1.5">
            {item.quotes.map((q) => (
              <li key={q.review_id} className="flex gap-1.5 text-xs leading-relaxed">
                <Quote className="mt-0.5 h-3 w-3 shrink-0 text-subtle-foreground" />
                <span className="min-w-0">
                  {q.quote}
                  <span className="tnum ml-1.5 text-subtle-foreground">{fmtDay(q.written_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs">
          <span className="text-muted-foreground">
            다르게 말한 리뷰 <span className="tnum font-medium">{item.opposite_cnt}</span>건
          </span>
          {activeActions > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 font-medium text-accent-foreground">
              <ListChecks className="h-3 w-3" />
              실행 과제 진행 중
            </span>
          )}
          <span className="ml-auto inline-flex items-center gap-0.5 font-medium text-primary">
            근거 리뷰 {item.related_cnt}건 보기
            <ChevronRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
