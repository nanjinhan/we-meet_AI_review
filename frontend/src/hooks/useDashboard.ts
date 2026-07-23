"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type Dashboard = components["schemas"]["DashboardOut"];
export type Range = "4w" | "8w" | "12w";

export function useDashboard(storeId: number | undefined, range: Range) {
  return useQuery({
    queryKey: ["dashboard", storeId, range],
    queryFn: () => api<Dashboard>(`/stores/${storeId}/dashboard?range=${range}`),
    enabled: storeId != null,
  });
}
