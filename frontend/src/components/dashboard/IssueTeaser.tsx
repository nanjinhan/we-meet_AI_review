"use client";

import { ChevronRight, ScanSearch } from "lucide-react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Range } from "@/hooks/useDashboard";
import { useInsights } from "@/hooks/useInsights";
import { insightsHref } from "@/lib/insight-copy";

const TOP = 3;

/**
 * 대시보드의 '반복 문제 후보' — 불만이 많이 언급된 항목을 건수·근거 문장과 함께 보여주고,
 * 누르면 근거 진단 화면의 해당 항목 근거로 바로 간다. 집계는 서버가 한다(프론트 계산 없음).
 */
export function IssueTeaser({ storeId, range }: { storeId: number; range: Range }) {
  const { data, isLoading, isError } = useInsights(storeId, range);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-1.5">
            <ScanSearch className="h-4 w-4 text-primary" />
            반복 문제 후보
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            불만이 언급된 리뷰가 많은 항목입니다. 눌러서 근거 리뷰를 확인하세요.
          </p>
        </div>
        <Link
          href={insightsHref({ range })}
          className="inline-flex shrink-0 items-center gap-0.5 text-xs font-medium text-primary hover:underline"
        >
          근거 진단 전체
          <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </CardHeader>
      <CardContent className="space-y-2 pt-3">
        {isLoading && <Skeleton className="h-28" />}
        {isError && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            근거 요약을 불러오지 못했습니다.
          </p>
        )}
        {data && data.issues.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            이 기간의 분석 리뷰에서 불만으로 분류된 항목이 없습니다.
          </p>
        )}
        {data?.issues.slice(0, TOP).map((item) => (
          <Link
            key={item.aspect}
            href={insightsHref({ aspect: item.aspect, polarity: "neg", range })}
            className="flex items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-muted"
          >
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-baseline gap-x-2 text-sm font-semibold">
                {item.aspect}
                <span className="tnum text-xs font-normal text-muted-foreground">
                  분석 리뷰 {item.analyzed_cnt}건 중{" "}
                  <span className="font-semibold text-chart-neg">{item.related_cnt}건</span> ·{" "}
                  {item.range_weeks}주 중 {item.weeks_mentioned}주
                </span>
              </p>
              {item.quotes[0] && (
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  “{item.quotes[0].quote}”
                </p>
              )}
              {!item.enough && (
                <p className="mt-0.5 text-[11px] text-amber-700">
                  {data.issue_min_related}건 미만 — 반복이라고 말하기 이름
                </p>
              )}
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-subtle-foreground" />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
