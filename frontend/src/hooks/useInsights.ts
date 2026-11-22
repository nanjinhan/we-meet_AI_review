"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Range } from "@/hooks/useDashboard";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import type { Polarity } from "@/lib/insight-copy";

export type Insights = components["schemas"]["InsightsOut"];
export type InsightItem = components["schemas"]["InsightItem"];
export type Coverage = components["schemas"]["Coverage"];
export type Evidence = components["schemas"]["EvidenceOut"];
export type EvidenceReview = components["schemas"]["EvidenceReview"];
export type ReviewCheck = components["schemas"]["ReviewCheck"];
export type ReviewsPage = components["schemas"]["ReviewsPage"];

export type EvidenceTarget = { aspect: string; polarity: Polarity };

/** 항목별 근거 요약(문제 후보·강점) + 분석 범위 + 검토 신호. asOf 는 리포트 기준 주를 볼 때만. */
export function useInsights(storeId: number | undefined, range: Range, asOf?: string) {
  return useQuery({
    queryKey: ["insights", storeId, range, asOf ?? null],
    queryFn: () =>
      api<Insights>(
        `/stores/${storeId}/insights?range=${range}` + (asOf ? `&as_of=${asOf}` : ""),
      ),
    enabled: storeId != null,
  });
}

/** 항목 하나의 근거 리뷰 원문·근거 문장·반대 의견. target 이 없으면 호출하지 않는다. */
export function useEvidence(
  storeId: number | undefined,
  target: EvidenceTarget | null,
  range: Range,
  asOf?: string,
) {
  return useQuery({
    queryKey: ["evidence", storeId, target?.aspect, target?.polarity, range, asOf ?? null],
    queryFn: () =>
      api<Evidence>(
        `/stores/${storeId}/insights/evidence?aspect=${encodeURIComponent(target!.aspect)}` +
          `&polarity=${target!.polarity}&range=${range}` +
          (asOf ? `&as_of=${asOf}` : ""),
      ),
    enabled: storeId != null && target != null,
  });
}

/** 분석 제외 내역 — 점주가 이유와 함께 뺀 리뷰들. */
export function useExcludedReviews(storeId: number | undefined) {
  return useQuery({
    queryKey: ["excluded", storeId],
    queryFn: () => api<ReviewsPage>(`/stores/${storeId}/reviews?excluded=true&limit=50`),
    enabled: storeId != null,
  });
}

/**
 * 리뷰를 분석에서 제외/다시 포함. 집계가 바뀌므로 관련 화면 캐시를 전부 새로 받는다.
 * (서버가 해당 주 통계를 즉시 다시 계산한다 — 대시보드·비교·근거가 같은 수치를 보게 된다.)
 */
export function useSetExclusion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { reviewId: number; excluded: boolean; reason?: string }) =>
      api(`/reviews/${v.reviewId}/exclusion`, {
        method: "PUT",
        body: JSON.stringify({ excluded: v.excluded, reason: v.reason ?? null }),
      }),
    onSuccess: () => {
      for (const key of ["insights", "evidence", "excluded", "dashboard", "compare", "actions", "reviews"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
