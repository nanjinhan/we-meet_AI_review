"use client";

import { Copy, Info, RotateCcw, SearchCheck, Star } from "lucide-react";
import { ExcludeControl } from "@/components/insights/ExcludeControl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ReviewCheck,
  useExcludedReviews,
  useSetExclusion,
} from "@/hooks/useInsights";
import { fmtDay, PLATFORM_LABEL } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

const KIND: Record<ReviewCheck["kind"], { label: string; desc: string; tone: string }> = {
  duplicate_record: {
    label: "중복 기록으로 보임",
    desc: "본문과 날짜가 같은 리뷰가 서로 다른 수집 경로에 있습니다. 같은 리뷰가 두 번 들어온 것이라면 한 건을 제외해 두 번 세지 않게 할 수 있어요.",
    tone: "bg-level-warn/15 text-amber-700",
  },
  similar_text: {
    label: "같은 문장 반복",
    desc: "서로 다른 작성 기록에 같은 문장이 있습니다. 각자 비슷한 경험을 쓴 것일 수 있으니 원문을 보고 판단하세요.",
    tone: "bg-muted text-muted-foreground",
  },
};

function CheckCard({ check }: { check: ReviewCheck }) {
  const kind = KIND[check.kind];
  return (
    <div className="space-y-2.5 rounded-xl border border-border p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold",
            kind.tone,
          )}
        >
          <Copy className="h-3 w-3" />
          {kind.label}
        </span>
        <span className="tnum text-xs text-muted-foreground">리뷰 {check.reviews.length}건</span>
      </div>
      <p className="rounded-lg bg-muted px-3 py-2 text-sm leading-relaxed">“{check.text}”</p>
      <p className="text-xs leading-relaxed text-muted-foreground">{kind.desc}</p>
      <ul className="space-y-2">
        {check.reviews.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
            <span className="font-semibold">{r.author_masked ?? "작성자 없음"}</span>
            {r.rating != null && (
              <span className="tnum inline-flex items-center gap-0.5 text-muted-foreground">
                <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
                {r.rating}
              </span>
            )}
            <span className="tnum text-muted-foreground">{fmtDay(r.written_at)}</span>
            <span className="text-muted-foreground">{PLATFORM_LABEL[r.platform] ?? r.platform}</span>
            <span className="ml-auto" />
            <ExcludeControl reviewId={r.id} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 검토가 필요한 리뷰 + 분석 제외 내역.
 * 여기서 시스템이 하는 일은 '찾아서 보여주기'까지다 — 가짜 리뷰로 판정하지 않고 자동으로 빼지도 않는다.
 * 제외는 점주가 이유와 함께 하고, 언제든 되돌릴 수 있다.
 */
export function ReviewChecks({
  checks,
  storeId,
}: {
  checks: ReviewCheck[];
  storeId: number;
}) {
  const excluded = useExcludedReviews(storeId);
  const restore = useSetExclusion();
  const log = excluded.data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <SearchCheck className="h-4 w-4 text-primary" />
          확인이 필요한 리뷰
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          분석 수치에 영향을 줄 수 있어 한 번 확인해 볼 만한 리뷰입니다.
        </p>
      </CardHeader>
      <CardContent className="space-y-4 pt-3">
        {checks.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            이 기간에는 중복 기록이나 같은 문장이 반복된 리뷰가 없습니다.
          </p>
        ) : (
          <div className="space-y-3">
            {checks.map((check) => (
              <CheckCard key={`${check.kind}-${check.reviews.map((r) => r.id).join("-")}`} check={check} />
            ))}
          </div>
        )}

        <p className="flex gap-1.5 text-xs leading-relaxed text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle-foreground" />
          <span>
            이 목록은 가짜 리뷰 판정이 아닙니다. 부정적인 내용이라는 이유로, 또는 글이 짧다는 이유로
            리뷰의 비중을 낮추지 않으며, 어떤 리뷰도 자동으로 제외하지 않습니다.
          </span>
        </p>

        <div className="space-y-2 border-t border-border pt-4">
          <p className="tnum text-sm font-semibold">분석 제외 내역 {log.length}건</p>
          {log.length === 0 ? (
            <p className="text-xs text-muted-foreground">분석에서 제외한 리뷰가 없습니다.</p>
          ) : (
            <ul className="space-y-2">
              {log.map((r) => (
                <li key={r.id} className="space-y-1.5 rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold">{r.author_masked ?? "작성자 없음"}</span>
                    <span className="tnum text-muted-foreground">{fmtDay(r.written_at)}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      이유: {r.exclude_reason ?? "기록 없음"}
                    </span>
                    <button
                      disabled={restore.isPending}
                      onClick={() => restore.mutate({ reviewId: r.id, excluded: false })}
                      className="ml-auto inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                      <RotateCcw className="h-3 w-3" />
                      다시 포함
                    </button>
                  </div>
                  <p className="text-xs leading-relaxed text-muted-foreground">{r.body}</p>
                </li>
              ))}
            </ul>
          )}
          {restore.isError && (
            <p className="text-xs text-destructive">되돌리지 못했습니다. 다시 시도해 주세요.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
