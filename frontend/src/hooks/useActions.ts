"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type Action = components["schemas"]["ActionOut"];
export type ActionCreate = components["schemas"]["ActionCreate"];
export type ActionUpdate = components["schemas"]["ActionUpdate"];

/** 실행 과제 목록 + 실행 전/후 관측(서버가 리뷰에서 매번 다시 센다). */
export function useActions(storeId: number | undefined) {
  return useQuery({
    queryKey: ["actions", storeId],
    queryFn: () => api<Action[]>(`/stores/${storeId}/actions`),
    enabled: storeId != null,
  });
}

export function useCreateAction(storeId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ActionCreate) =>
      api<Action>(`/stores/${storeId}/actions`, { method: "POST", body: JSON.stringify(payload) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions", storeId] }),
  });
}

export function useUpdateAction(storeId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; patch: ActionUpdate }) =>
      api<Action>(`/actions/${v.id}`, { method: "PATCH", body: JSON.stringify(v.patch) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions", storeId] }),
  });
}

export function useDeleteAction(storeId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/actions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions", storeId] }),
  });
}
