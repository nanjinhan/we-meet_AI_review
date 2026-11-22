"use client";

import { ArrowRight, Check, Info, ListChecks, RotateCcw, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { type Action, useDeleteAction, useUpdateAction } from "@/hooks/useActions";
import type { EvidenceTarget } from "@/hooks/useInsights";
import { fmtDay, POLARITY_LABEL, type Polarity } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<string, string> = { active: "진행 중", done: "완료", dropped: "중단" };

function Observation({ action }: { action: Action }) {
  const o = action.observation;
  const notStarted = o.after_days === 0;
  const cells = [
    {
      label: `실행 전 ${o.before_days / 7}주`,
      related: o.before_related_cnt,
      analyzed: o.before_analyzed_cnt,
      empty: "이 기간에 분석된 리뷰가 없습니다",
    },
    {
      label: notStarted ? "실행 후" : `실행 후 ${o.after_days}일`,
      related: o.after_related_cnt,
      analyzed: o.after_analyzed_cnt,
      empty: notStarted ? "아직 실행일 전입니다" : "아직 분석된 리뷰가 없습니다",
    },
  ];

  return (
    <div className="space-y-2">
      <div className="flex items-stretch gap-2">
        {cells.map((cell, i) => (
          <div key={cell.label} className="flex flex-1 items-center gap-2">
            {i === 1 && <ArrowRight className="h-4 w-4 shrink-0 text-subtle-foreground" />}
            <div className="flex-1 rounded-lg border border-border px-3 py-2">
              <p className="text-[11px] text-muted-foreground">{cell.label}</p>
              {cell.analyzed > 0 ? (
                <p className="tnum text-sm text-muted-foreground">
                  리뷰 {cell.analyzed}건 중{" "}
                  <span className="text-lg font-semibold text-foreground">{cell.related}</span>건
                </p>
              ) : (
                <p className="py-1 text-xs text-subtle-foreground">{cell.empty}</p>
              )}
            </div>
          </div>
        ))}
      </div>
      {!notStarted && !o.enough && (
        <p className="rounded-md bg-level-warn/10 px-2.5 py-1.5 text-[11px] text-amber-700">
          실행 후 분석된 리뷰가 {o.min_analyzed}건 미만이라 아직 비교하기 이릅니다.
        </p>
      )}
    </div>
  );
}

/**
 * 실행 과제 목록 — 기록한 행동과, 실행일 전후로 같은 항목이 리뷰에 나타난 건수.
 * 건수만 나란히 보여주고 '효과 있음/없음'을 판정하지 않는다.
 */
export function ActionList({
  actions,
  storeId,
  onOpenEvidence,
}: {
  actions: Action[];
  storeId: number;
  onOpenEvidence: (target: EvidenceTarget) => void;
}) {
  const update = useUpdateAction(storeId);
  const remove = useDeleteAction(storeId);
  const busy = update.isPending || remove.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <ListChecks className="h-4 w-4 text-primary" />
          실행 과제
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          근거를 보고 고른 행동과, 실행일 이후 리뷰에서의 관측입니다.
        </p>
      </CardHeader>
      <CardContent className="space-y-3 pt-3">
        {actions.length === 0 && (
          <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            아직 기록한 실행 과제가 없습니다. 위 항목 카드를 눌러 근거를 확인한 뒤, 해볼 일을 하나
            기록해 보세요.
          </p>
        )}

        {actions.map((a) => {
          const polarity = a.polarity as Polarity;
          return (
            <div
              key={a.id}
              className={cn(
                "space-y-3 rounded-xl border border-border p-3.5",
                a.status !== "active" && "bg-muted/50",
              )}
            >
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-sm font-semibold",
                      a.status === "dropped" && "text-muted-foreground line-through",
                    )}
                  >
                    {a.title}
                  </p>
                  <p className="tnum mt-0.5 text-xs text-muted-foreground">
                    <button
                      onClick={() => onOpenEvidence({ aspect: a.aspect, polarity })}
                      className="font-medium text-primary hover:underline"
                    >
                      {a.aspect} {POLARITY_LABEL[polarity]}
                    </button>
                    {" · "}실행일 {fmtDay(a.started_on)}
                    {a.note && <> · {a.note}</>}
                  </p>
                </div>
                <span
                  className={cn(
                    "shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold",
                    a.status === "active" && "bg-accent text-accent-foreground",
                    a.status === "done" && "bg-delta-up/10 text-delta-up",
                    a.status === "dropped" && "bg-muted text-muted-foreground",
                  )}
                >
                  {STATUS_LABEL[a.status] ?? a.status}
                </span>
              </div>

              <Observation action={a} />

              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                {a.status === "active" ? (
                  <>
                    <button
                      disabled={busy}
                      onClick={() => update.mutate({ id: a.id, patch: { status: "done" } })}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                      <Check className="h-3 w-3" />
                      완료로 표시
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => update.mutate({ id: a.id, patch: { status: "dropped" } })}
                      className="rounded-md border border-border px-2 py-1 font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                      중단
                    </button>
                  </>
                ) : (
                  <button
                    disabled={busy}
                    onClick={() => update.mutate({ id: a.id, patch: { status: "active" } })}
                    className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                  >
                    <RotateCcw className="h-3 w-3" />
                    다시 진행
                  </button>
                )}
                <button
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`‘${a.title}’ 기록을 삭제할까요?`)) remove.mutate(a.id);
                  }}
                  className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 font-medium text-subtle-foreground hover:bg-muted hover:text-destructive disabled:opacity-50"
                >
                  <Trash2 className="h-3 w-3" />
                  삭제
                </button>
              </div>
            </div>
          );
        })}

        {actions.length > 0 && (
          <p className="flex gap-1.5 text-xs leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle-foreground" />
            <span>
              전후 건수는 관측일 뿐 효과 판정이 아닙니다. 계절·행사·리뷰 수 변화 같은 다른 요인이 함께
              작용할 수 있어, 이 화면은 ‘개선됐다’고 결론 내리지 않습니다.
            </span>
          </p>
        )}
        {(update.isError || remove.isError) && (
          <p className="text-xs text-destructive">변경하지 못했습니다. 다시 시도해 주세요.</p>
        )}
      </CardContent>
    </Card>
  );
}
