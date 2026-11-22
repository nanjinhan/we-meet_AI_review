"use client";

import { CalendarClock, ThumbsUp, TriangleAlert } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";
import { ActionList } from "@/components/insights/ActionList";
import { CoverageCard } from "@/components/insights/CoverageCard";
import { EvidenceDrawer } from "@/components/insights/EvidenceDrawer";
import { InsightCard } from "@/components/insights/InsightCard";
import { ReviewChecks } from "@/components/insights/ReviewChecks";
import { FadeIn } from "@/components/motion/fade-in";
import { useStore } from "@/components/store-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useActions } from "@/hooks/useActions";
import type { Range } from "@/hooks/useDashboard";
import { type EvidenceTarget, type InsightItem, useInsights } from "@/hooks/useInsights";
import { fmtPeriod } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

const RANGES: { value: Range; label: string }[] = [
  { value: "4w", label: "4주" },
  { value: "8w", label: "8주" },
  { value: "12w", label: "12주" },
];

function SectionTitle({
  icon: Icon,
  title,
  desc,
  tone,
}: {
  icon: typeof TriangleAlert;
  title: string;
  desc: string;
  tone: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone)} />
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
    </div>
  );
}

function InsightsContent() {
  const { store, isLoading: storeLoading, isError: storeError } = useStore();
  const router = useRouter();
  const params = useSearchParams();

  // 화면 상태는 전부 URL 에 둔다 — 대시보드·리포트에서 특정 항목의 근거로 바로 들어올 수 있게.
  const rangeParam = params.get("range");
  const range: Range = RANGES.some((r) => r.value === rangeParam) ? (rangeParam as Range) : "4w";
  const asOfParam = params.get("as_of") ?? "";
  const asOf = /^\d{4}-\d{2}-\d{2}$/.test(asOfParam) ? asOfParam : undefined;
  const aspect = params.get("aspect");
  const target: EvidenceTarget | null = aspect
    ? { aspect, polarity: params.get("polarity") === "pos" ? "pos" : "neg" }
    : null;

  const navigate = useCallback(
    (change: (q: URLSearchParams) => void) => {
      const q = new URLSearchParams(params.toString());
      change(q);
      const s = q.toString();
      router.replace(s ? `/insights?${s}` : "/insights", { scroll: false });
    },
    [params, router],
  );

  const openEvidence = (t: EvidenceTarget) =>
    navigate((q) => {
      q.set("aspect", t.aspect);
      q.set("polarity", t.polarity);
    });
  const closeEvidence = useCallback(
    () =>
      navigate((q) => {
        q.delete("aspect");
        q.delete("polarity");
      }),
    [navigate],
  );

  const { data, isLoading, isError } = useInsights(store?.id, range, asOf);
  const actions = useActions(store?.id);

  const activeActions = (item: InsightItem) =>
    (actions.data ?? []).filter(
      (a) => a.status === "active" && a.aspect === item.aspect && a.polarity === item.polarity,
    ).length;

  const grid = (items: InsightItem[], empty: string) =>
    items.length === 0 ? (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">{empty}</CardContent>
      </Card>
    ) : (
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item) => (
          <InsightCard
            key={`${item.aspect}-${item.polarity}`}
            item={item}
            minRelated={data?.issue_min_related ?? 3}
            activeActions={activeActions(item)}
            onOpen={() => openEvidence({ aspect: item.aspect, polarity: item.polarity })}
          />
        ))}
      </div>
    );

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-xl font-bold">근거 진단</h1>
          <p className="text-sm text-muted-foreground">
            {store
              ? `${store.name} — 분석 결과마다 어떤 리뷰를 근거로 했는지, 몇 건 중 몇 건인지 보여드려요`
              : "분석 결과의 근거 리뷰와 건수"}
          </p>
        </div>
        <div className="flex rounded-lg border border-border bg-card p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => navigate((q) => q.set("range", r.value))}
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

      {asOf && data && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-3 p-3.5 text-sm">
            <CalendarClock className="h-4 w-4 shrink-0 text-primary" />
            <span className="tnum min-w-0 flex-1">
              지난 기간({fmtPeriod(data.coverage.period_start, data.coverage.period_end)})의 근거를
              보고 있습니다. 주간 리포트와 같은 기간입니다.
            </span>
            <Button variant="outline" size="sm" onClick={() => navigate((q) => q.delete("as_of"))}>
              최신 기간으로 보기
            </Button>
          </CardContent>
        </Card>
      )}

      {(storeLoading || isLoading) && (
        <div className="space-y-4">
          <Skeleton className="h-44" />
          <div className="grid gap-3 md:grid-cols-2">
            <Skeleton className="h-48" />
            <Skeleton className="h-48" />
          </div>
        </div>
      )}

      {(storeError || isError) && !isLoading && !storeLoading && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            근거 진단을 불러오지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.
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

      {data && store && (
        <div className="space-y-6">
          <FadeIn>
            <CoverageCard data={data} />
          </FadeIn>

          <FadeIn delay={0.05} className="space-y-3">
            <SectionTitle
              icon={TriangleAlert}
              tone="text-chart-neg"
              title="반복 문제 후보"
              desc="불만이 언급된 항목을 리뷰 건수가 많은 순으로 보여드려요. 카드를 누르면 근거 리뷰 원문이 열립니다."
            />
            {grid(
              data.issues,
              data.coverage.analyzed_cnt === 0
                ? "이 기간에 분석된 리뷰가 없습니다."
                : "이 기간의 분석 리뷰에서 불만으로 분류된 항목이 없습니다.",
            )}
          </FadeIn>

          <FadeIn delay={0.1} className="space-y-3">
            <SectionTitle
              icon={ThumbsUp}
              tone="text-chart-pos"
              title="호평이 모인 항목"
              desc="같은 기준(분석 리뷰 중 몇 건)으로 센 호평 언급입니다."
            />
            {grid(
              data.strengths,
              data.coverage.analyzed_cnt === 0
                ? "이 기간에 분석된 리뷰가 없습니다."
                : "이 기간의 분석 리뷰에서 호평으로 분류된 항목이 없습니다.",
            )}
          </FadeIn>

          <FadeIn delay={0.15}>
            <ActionList actions={actions.data ?? []} storeId={store.id} onOpenEvidence={openEvidence} />
          </FadeIn>

          <FadeIn delay={0.2}>
            <ReviewChecks checks={data.checks} storeId={store.id} />
          </FadeIn>
        </div>
      )}

      <EvidenceDrawer
        storeId={store?.id}
        target={target}
        range={range}
        asOf={asOf}
        onClose={closeEvidence}
      />
    </section>
  );
}

export default function InsightsPage() {
  // useSearchParams 는 Suspense 경계가 필요 (Next.js App Router)
  return (
    <Suspense>
      <InsightsContent />
    </Suspense>
  );
}
