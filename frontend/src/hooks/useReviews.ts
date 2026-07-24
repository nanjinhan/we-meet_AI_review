"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";

export type ReviewItem = components["schemas"]["ReviewItem"];
export type ReviewsPage = components["schemas"]["ReviewsPage"];

/** 인박스 필터 칩 — URL ?filter= 값과 1:1 (FRONTEND.md §4) */
export type InboxFilter = "all" | "neg" | "urgent" | "unanswered";

function filterQuery(filter: InboxFilter): string {
  switch (filter) {
    case "neg":
      return "&sentiment=neg";
    case "urgent":
      return "&urgent=true";
    case "unanswered":
      return "&answered=false";
    default:
      return "";
  }
}

export function useReviews(storeId: number | undefined, filter: InboxFilter) {
  return useInfiniteQuery({
    queryKey: ["reviews", storeId, filter],
    queryFn: ({ pageParam }) =>
      api<ReviewsPage>(
        `/stores/${storeId}/reviews?limit=20${filterQuery(filter)}` +
          (pageParam ? `&cursor=${pageParam}` : ""),
      ),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: storeId != null,
  });
}
