import { Info } from "lucide-react";
import { SufficiencyBadge } from "@/components/insights/SufficiencyBadge";
import { Card, CardContent } from "@/components/ui/card";
import type { Insights } from "@/hooks/useInsights";
import { fmtPeriod, SUFFICIENCY } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

/**
 * 분석 범위 — 아래 모든 "N건 중"의 분모가 무엇이고 무엇이 빠졌는지.
 * 빠진 리뷰(분석 전·실패·제외·작성일 없음)를 숨기지 않고 건수로 보여준다.
 */
export function CoverageCard({ data }: { data: Insights }) {
  const c = data.coverage;
  const s = data.sufficiency;
  const cells = [
    { label: "분석에 쓰인 리뷰", value: c.analyzed_cnt, strong: true, hint: "아래 모든 '몇 건 중'의 기준" },
    { label: "분석 전", value: c.pending_cnt, hint: "수집됐지만 아직 분석되지 않음" },
    { label: "분석 실패", value: c.failed_cnt, hint: "분석 중 오류가 난 리뷰" },
    { label: "분석 제외", value: c.excluded_cnt, hint: "점주가 이유를 남기고 뺀 리뷰" },
    { label: "작성일 없음", value: c.undated_cnt, hint: "날짜가 없어 기간에 넣지 못함(전체 누적)" },
  ];

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-muted-foreground">분석 범위</p>
            <p className="tnum mt-1 text-lg font-semibold tracking-tight">
              {fmtPeriod(c.period_start, c.period_end)}
              <span className="ml-2 text-sm font-normal text-subtle-foreground">
                {data.range_weeks}주 · 수집 리뷰 {c.collected_cnt.toLocaleString("ko-KR")}건
              </span>
            </p>
          </div>
          <div className="sm:text-right">
            <SufficiencyBadge level={s.level} />
            <p className="mt-1 text-[11px] text-subtle-foreground">
              분석 리뷰 {s.low_below}건 미만 ‘적음’ · {s.good_from}건 이상 ‘충분한 편’
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {cells.map((cell) => (
            <div
              key={cell.label}
              title={cell.hint}
              className={cn(
                "rounded-lg border border-border px-3 py-2",
                cell.strong && "border-primary/30 bg-accent",
              )}
            >
              <p className="text-[11px] text-muted-foreground">{cell.label}</p>
              <p
                className={cn(
                  "tnum text-xl font-semibold tracking-tight",
                  !cell.strong && cell.value === 0 && "text-subtle-foreground",
                )}
              >
                {cell.value.toLocaleString("ko-KR")}
                <span className="ml-0.5 text-xs font-normal text-subtle-foreground">건</span>
              </p>
            </div>
          ))}
        </div>

        <ul className="space-y-1 text-xs leading-relaxed text-muted-foreground">
          <li className="flex gap-1.5">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle-foreground" />
            <span>
              리뷰를 남긴 고객의 경험만 집계한 결과입니다. 전체 방문 고객의 비율이 아니며, 건수는
              ‘고객 수’가 아니라 ‘리뷰 수’입니다.
            </span>
          </li>
          <li className="flex gap-1.5">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle-foreground" />
            <span>
              자료 충분도는 분석 리뷰 수에 따른 안내이며 통계적 신뢰도 수치가 아닙니다.{" "}
              {SUFFICIENCY[s.level].hint}
            </span>
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}
