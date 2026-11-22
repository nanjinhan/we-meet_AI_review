"use client";

import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Star, X } from "lucide-react";
import { useEffect, useState } from "react";
import { ActionForm } from "@/components/insights/ActionForm";
import { ExcludeControl } from "@/components/insights/ExcludeControl";
import { HighlightedBody } from "@/components/review/HighlightedBody";
import { Skeleton } from "@/components/ui/skeleton";
import type { Range } from "@/hooks/useDashboard";
import {
  type Evidence,
  type EvidenceReview,
  type EvidenceTarget,
  useEvidence,
} from "@/hooks/useInsights";
import {
  aspectCopy,
  fmtDay,
  fmtPeriod,
  PLATFORM_LABEL,
  POLARITY_LABEL,
  type Polarity,
} from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

function ReviewRow({
  review,
  polarity,
  canExclude,
}: {
  review: EvidenceReview;
  polarity: Polarity;
  canExclude: boolean;
}) {
  return (
    <li className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">{review.author_masked ?? "작성자 없음"}</span>
        {review.rating != null && (
          <span className="tnum inline-flex items-center gap-0.5">
            <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
            {review.rating}
          </span>
        )}
        <span className="tnum">{fmtDay(review.written_at)}</span>
        <span>{PLATFORM_LABEL[review.platform] ?? review.platform}</span>
        {!review.quote && (
          <span
            className="rounded bg-muted px-1.5 py-0.5 text-[10px]"
            title="이 리뷰는 근거 문장이 따로 저장되지 않아 본문 전체가 근거입니다"
          >
            문장 표시 없음
          </span>
        )}
      </div>
      <HighlightedBody
        body={review.body}
        highlights={review.quote ? [{ text: review.quote, polarity }] : []}
      />
      {canExclude && <ExcludeControl reviewId={review.id} />}
    </li>
  );
}

function Facts({ data }: { data: Evidence }) {
  const c = data.coverage;
  const label = POLARITY_LABEL[data.polarity];
  const copy = aspectCopy(data.aspect, data.polarity);
  const max = Math.max(1, ...data.weekly.map((w) => w.related_cnt));
  const skipped = c.pending_cnt + c.failed_cnt + c.excluded_cnt;

  const rows: { term: string; body: React.ReactNode }[] = [
    {
      term: "분석 범위",
      body: (
        <span className="tnum">
          {fmtPeriod(c.period_start, c.period_end)}에 작성된 리뷰 중 분석에 쓰인 {c.analyzed_cnt}건
          {skipped > 0 && (
            <span className="text-subtle-foreground">
              {" "}
              (분석 전 {c.pending_cnt} · 실패 {c.failed_cnt} · 제외 {c.excluded_cnt}건은 빠짐)
            </span>
          )}
        </span>
      ),
    },
    {
      term: "관련 리뷰",
      body: (
        <span className="tnum">
          {data.aspect} {label} <strong className="font-semibold">{data.related_cnt}건</strong> / 분석
          리뷰 {data.analyzed_cnt}건
          {!data.enough && data.related_cnt > 0 && (
            <span className="ml-1.5 rounded bg-level-warn/15 px-1.5 py-0.5 text-[11px] text-amber-700">
              {data.issue_min_related}건 미만 — 반복이라고 말하기 이름
            </span>
          )}
        </span>
      ),
    },
    {
      term: "주별 언급",
      body: (
        <div className="flex items-end gap-2">
          {data.weekly.map((w) => (
            <div
              key={w.week_start}
              className="flex flex-1 flex-col items-center gap-1"
              title={`${fmtDay(w.week_start)} 주 — 분석 리뷰 ${w.analyzed_cnt}건 중 ${w.related_cnt}건`}
            >
              <span className="tnum text-[11px] font-medium">{w.related_cnt}</span>
              <div className="flex h-8 w-full max-w-10 items-end rounded bg-muted">
                <div
                  className={cn(
                    "w-full rounded",
                    data.polarity === "neg" ? "bg-chart-neg" : "bg-chart-pos",
                  )}
                  style={{ height: `${(w.related_cnt / max) * 100}%` }}
                />
              </div>
              <span className="tnum text-[10px] text-subtle-foreground">{fmtDay(w.week_start)}</span>
            </div>
          ))}
        </div>
      ),
    },
    {
      term: "함께 나온 말",
      body:
        data.keywords.length > 0 ? (
          <span className="flex flex-wrap gap-1.5">
            {data.keywords.map((k) => (
              <span key={k.keyword} className="tnum rounded-full bg-muted px-2 py-0.5 text-[11px]">
                {k.keyword} {k.count}건
              </span>
            ))}
          </span>
        ) : (
          <span className="text-subtle-foreground">관련 리뷰에 붙은 키워드가 없습니다</span>
        ),
    },
    {
      term: "다른 경험",
      body: (
        <span className="tnum">
          같은 항목을 {POLARITY_LABEL[data.polarity === "neg" ? "pos" : "neg"]}으로 말한 리뷰{" "}
          {data.opposite_cnt}건{data.opposite_cnt > 0 && " (아래에서 원문 확인)"}
        </span>
      ),
    },
    {
      term: "자료 한계",
      body: "리뷰에 적힌 경험을 센 결과이며, 전체 방문 고객 중 비율이 아닙니다. 리뷰에 없는 방문 시간·원인은 추정해 넣지 않았습니다.",
    },
    {
      term: "직접 확인할 것",
      body: (
        <ul className="list-disc space-y-0.5 pl-4">
          {copy.checks.map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      ),
    },
  ];

  return (
    <dl className="divide-y divide-border rounded-xl border border-border text-xs leading-relaxed">
      {rows.map((row) => (
        <div key={row.term} className="grid grid-cols-[5.5rem_1fr] gap-3 px-3.5 py-2.5">
          <dt className="font-medium text-muted-foreground">{row.term}</dt>
          <dd className="min-w-0">{row.body}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * 근거 패널 — 항목 하나에 대해 "어떤 리뷰를 근거로, 몇 건 중 몇 건인지"를 원문과 함께 보여준다.
 * 요약 문장의 숫자는 아래 목록의 길이와 항상 같다(서버가 같은 행에서 센다).
 */
export function EvidenceDrawer({
  storeId,
  target,
  range,
  asOf,
  onClose,
}: {
  storeId: number | undefined;
  target: EvidenceTarget | null;
  range: Range;
  asOf?: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError } = useEvidence(storeId, target, range, asOf);
  const [showOpposite, setShowOpposite] = useState(false);

  useEffect(() => {
    setShowOpposite(false);
  }, [target?.aspect, target?.polarity]);

  // Esc 로 닫기
  useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target, onClose]);

  const label = target ? POLARITY_LABEL[target.polarity] : "";

  return (
    <AnimatePresence>
      {target && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40"
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={`${target.aspect} ${label} 근거`}
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 320 }}
            className="fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[90vh] w-full max-w-2xl flex-col rounded-t-2xl border border-border bg-card shadow-xl"
          >
            <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
              <div className="min-w-0">
                <p className="text-xs font-medium text-muted-foreground">근거 확인</p>
                <h2 className="mt-0.5 flex items-center gap-2 text-base font-bold">
                  {target.aspect}
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                      target.polarity === "neg"
                        ? "bg-chart-neg/10 text-chart-neg"
                        : "bg-chart-pos/10 text-chart-pos",
                    )}
                  >
                    {label}
                  </span>
                </h2>
              </div>
              <button
                onClick={onClose}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted"
                aria-label="닫기"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4 overflow-y-auto px-5 py-4">
              {isLoading && (
                <div className="space-y-3">
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-56" />
                  <Skeleton className="h-24" />
                </div>
              )}
              {isError && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  근거를 불러오지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.
                </p>
              )}

              {data && (
                <>
                  <p className="tnum text-sm leading-relaxed">
                    {fmtPeriod(data.coverage.period_start, data.coverage.period_end)}(
                    {data.range_weeks}주) 분석 리뷰{" "}
                    <strong className="font-semibold">{data.analyzed_cnt}건</strong> 중{" "}
                    <strong className="font-semibold">{data.related_cnt}건</strong>에서 {data.aspect}{" "}
                    관련 {label}이 언급됐습니다.
                  </p>

                  <Facts data={data} />

                  {storeId != null && (
                    <ActionForm storeId={storeId} aspect={data.aspect} polarity={data.polarity} />
                  )}

                  <section className="space-y-2">
                    <h3 className="tnum text-sm font-semibold">
                      근거 리뷰 {data.related_cnt}건
                      {data.truncated && (
                        <span className="ml-1.5 text-xs font-normal text-subtle-foreground">
                          (최근 {data.reviews.length}건만 표시)
                        </span>
                      )}
                    </h3>
                    {data.reviews.length === 0 ? (
                      <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
                        이 기간에 {data.aspect} 관련 {label}을 언급한 리뷰가 없습니다.
                      </p>
                    ) : (
                      <ul className="space-y-2">
                        {data.reviews.map((r) => (
                          <ReviewRow key={r.id} review={r} polarity={data.polarity} canExclude />
                        ))}
                      </ul>
                    )}
                  </section>

                  {data.opposite_cnt > 0 && (
                    <section className="space-y-2">
                      <button
                        onClick={() => setShowOpposite((v) => !v)}
                        className="tnum flex w-full items-center justify-between rounded-lg bg-muted px-3 py-2 text-left text-sm font-semibold"
                        aria-expanded={showOpposite}
                      >
                        다르게 말한 리뷰 {data.opposite_cnt}건
                        <ChevronDown
                          className={cn("h-4 w-4 transition-transform", showOpposite && "rotate-180")}
                        />
                      </button>
                      {showOpposite && (
                        <ul className="space-y-2">
                          {data.opposite_reviews.map((r) => (
                            <ReviewRow
                              key={r.id}
                              review={r}
                              polarity={data.polarity === "neg" ? "pos" : "neg"}
                              canExclude={false}
                            />
                          ))}
                          {data.opposite_cnt > data.opposite_reviews.length && (
                            <li className="tnum px-1 text-xs text-subtle-foreground">
                              최근 {data.opposite_reviews.length}건만 표시했습니다.
                            </li>
                          )}
                        </ul>
                      )}
                    </section>
                  )}
                </>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
