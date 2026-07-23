"use client";

import { Flame } from "lucide-react";
import { useState } from "react";
import { AspectBars } from "@/components/dashboard/AspectBars";
import { ScoreCard } from "@/components/dashboard/ScoreCard";
import { StatTiles } from "@/components/dashboard/StatTiles";
import { TrendChart } from "@/components/dashboard/TrendChart";
import { FadeIn } from "@/components/motion/fade-in";
import { useStore } from "@/components/store-provider";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard, type Range } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";

const RANGES: { value: Range; label: string }[] = [
  { value: "4w", label: "4주" },
  { value: "8w", label: "8주" },
  { value: "12w", label: "12주" },
];

function LoadingState() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-36" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[72px]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { store, isLoading: storeLoading, isError: storeError } = useStore();
  const [range, setRange] = useState<Range>("4w");
  const { data, isLoading, isError } = useDashboard(store?.id, range);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">대시보드</h1>
          <p className="text-sm text-muted-foreground">
            {store ? `${store.name}의 최근 ${range.replace("w", "주")} 평판 요약` : "매장 평판 요약"}
          </p>
        </div>
        <div className="flex rounded-lg border border-border bg-card p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => setRange(r.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                range === r.value
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {(storeLoading || isLoading) && <LoadingState />}

      {(storeError || isError) && !isLoading && !storeLoading && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            데이터를 불러오지 못했습니다. 백엔드(<code>localhost:8000</code>)가 실행 중인지
            확인해 주세요.
          </CardContent>
        </Card>
      )}

      {!storeLoading && !storeError && !store && !isLoading && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            등록된 매장이 없습니다. 온보딩에서 매장을 먼저 등록해 주세요.
          </CardContent>
        </Card>
      )}

      {data && (
        <div className="space-y-4">
          <FadeIn>
            <ScoreCard score={data.score} delta={data.score_delta} />
          </FadeIn>
          <FadeIn delay={0.05}>
            <StatTiles data={data} />
          </FadeIn>
          <div className="grid gap-4 lg:grid-cols-2">
            <FadeIn delay={0.1}>
              <TrendChart trend={data.trend} />
            </FadeIn>
            <FadeIn delay={0.15}>
              <AspectBars aspects={data.aspects} />
            </FadeIn>
          </div>
          <FadeIn delay={0.2}>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Flame className="h-4 w-4 text-chart-neg" />
                  급증 키워드
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2 pt-3">
                {data.keywords.length === 0 && (
                  <p className="text-sm text-muted-foreground">최근 급증한 키워드가 없습니다.</p>
                )}
                {data.keywords.map((k) => (
                  <Badge key={k} variant="accent">
                    {k}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          </FadeIn>
        </div>
      )}
    </section>
  );
}
