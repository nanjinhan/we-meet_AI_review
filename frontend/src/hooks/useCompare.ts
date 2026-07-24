"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import type { Range } from "@/hooks/useDashboard";

export type Compare = components["schemas"]["CompareOut"];
export type CompareAspect = components["schemas"]["CompareAspect"];

export function useCompare(storeId: number | undefined, range: Range) {
  return useQuery({
    queryKey: ["compare", storeId, range],
    queryFn: () => api<Compare>(`/stores/${storeId}/compare?range=${range}`),
    enabled: storeId != null,
  });
}
