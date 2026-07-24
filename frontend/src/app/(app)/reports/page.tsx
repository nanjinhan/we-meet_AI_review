"use client";

import { CalendarDays, FileText } from "lucide-react";
import { DiagnosisCard } from "@/components/report/DiagnosisCard";
import { PrescriptionList } from "@/components/report/PrescriptionList";
import { FadeIn } from "@/components/motion/fade-in";
import { useStore } from "@/components/store-provider";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useReport, type Diagnosis, type Prescription } from "@/hooks/useReport";
import { ApiError } from "@/lib/api";

// 진단 정렬 우선순위 — 심각한 것부터 보이게
const ORDER = ["crit", "warn", "opportunity", "strength"];

export default function ReportsPage() {
  const { store, isLoading: storeLoading } = useStore();
  const { data, isLoading, error } = useReport(store?.id);

  const notGenerated = error instanceof ApiError && error.status === 404;
  const diagnosis = ((data?.diagnosis ?? []) as Diagnosis[])
    .slice()
    .sort((a, b) => ORDER.indexOf(a.level) - ORDER.indexOf(b.level));
  const prescriptions = (data?.prescriptions ?? []) as Prescription[];

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">주간 리포트</h1>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {data ? (
            <>
              <CalendarDays className="h-3.5 w-3.5" />
              {data.week_start} 주차 · {store?.name}
            </>
          ) : (
            "AI가 진단하고 처방합니다"
          )}
        </p>
      </div>

      {(storeLoading || isLoading) && (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-48" />
        </div>
      )}

      {notGenerated && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
            <FileText className="h-8 w-8 text-subtle-foreground" />
            <p className="text-sm font-medium">아직 생성된 리포트가 없습니다</p>
            <p className="text-xs text-muted-foreground">
              리포트는 매주 월요일 자동 생성됩니다. (워커 실행 필요)
            </p>
          </CardContent>
        </Card>
      )}

      {error && !notGenerated && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            리포트를 불러오지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.
          </CardContent>
        </Card>
      )}

      {data && (
        <div className="space-y-4">
          <FadeIn>
            <div className="grid gap-3 md:grid-cols-2">
              {diagnosis.map((d, i) => (
                <DiagnosisCard key={i} item={d} index={i} />
              ))}
            </div>
          </FadeIn>
          <FadeIn delay={0.1}>
            <PrescriptionList items={prescriptions} reportId={data.id} />
          </FadeIn>
        </div>
      )}
    </section>
  );
}
