"use client";

import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type Report = components["schemas"]["ReportRead"];

/** 진단 1건 — diagnosis JSONB 의 실제 형태 (백엔드 프롬프트 스키마와 동일). */
export type Diagnosis = { level: string; title: string; evidence: string };
export type Prescription = { title: string; detail: string; expected_effect: string };

export function useReport(storeId: number | undefined) {
  return useQuery({
    queryKey: ["report", storeId],
    queryFn: () => api<Report>(`/stores/${storeId}/reports/latest`),
    enabled: storeId != null,
    // 리포트 미생성(404)은 정상 상태 — 재시도하지 않는다.
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });
}
