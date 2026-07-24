"use client";

import { Lightbulb, Users } from "lucide-react";
import { useState } from "react";
import { CompareBars } from "@/components/compare/CompareBars";
import { CompareTable } from "@/components/compare/CompareTable";
import { FadeIn } from "@/components/motion/fade-in";
import { useStore } from "@/components/store-provider";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCompare } from "@/hooks/useCompare";
import type { Range } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";

const RANGES: { value: Range; label: string }[] = [
  { value: "4w", label: "4주" },
  { value: "8w", label: "8주" },
  { value: "12w", label: "12주" },
];

export default function ComparePage() {
  const { store, isLoading: storeLoading } = useStore();
  const [range, setRange] = useState<Range>("4w");
  const { data, isLoading, isError } = useCompare(store?.id, range);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">경쟁매장 비교</h1>
          <p className="text-sm text-muted-foreground">
            {store ? `${store.name} vs 등록된 경쟁매장` : "우리 매장과 경쟁매장 비교"}
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

      {(storeLoading || isLoading) && (
        <div className="space-y-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-80" />
        </div>
      )}

      {isError && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            비교 데이터를 불러오지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.
          </CardContent>
        </Card>
      )}

      {data && (
        <div className="space-y-4">
          <FadeIn>
            <Card>
              <CardContent className="flex items-start gap-3 p-4">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                  <Lightbulb className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">인사이트</p>
                  <p className="mt-0.5 text-sm leading-relaxed">{data.insight}</p>
                </div>
              </CardContent>
            </Card>
          </FadeIn>

          {!data.has_competitors ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
                <Users className="h-8 w-8 text-subtle-foreground" />
                <p className="text-sm font-medium">등록된 경쟁매장이 없습니다</p>
                <p className="text-xs text-muted-foreground">
                  경쟁매장을 등록하면 항목별 비교를 볼 수 있어요.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              <FadeIn delay={0.05}>
                <CompareBars aspects={data.aspects} />
              </FadeIn>
              <FadeIn delay={0.1}>
                <CompareTable aspects={data.aspects} />
              </FadeIn>
            </>
          )}
        </div>
      )}
    </section>
  );
}
