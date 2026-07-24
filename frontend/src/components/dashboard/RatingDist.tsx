"use client";

import { Star } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Dashboard } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";

/** 별점 분포 — 평균 별점 + 5→1점 비중 바 (레퍼런스: cascal customer reviews 패널). */
export function RatingDist({
  dist,
  avgRating,
  totalReviews,
}: {
  dist: Dashboard["rating_dist"];
  avgRating: number | null;
  totalReviews: number;
}) {
  const rounded = Math.round(avgRating ?? 0);

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="text-center">
          <p className="text-xs font-medium text-muted-foreground">고객 별점</p>
          <p className="tnum mt-1 text-4xl font-semibold tracking-tight">
            {avgRating != null ? avgRating.toFixed(1) : "—"}
          </p>
          <p className="text-xs text-subtle-foreground">리뷰 {totalReviews.toLocaleString("ko-KR")}건</p>
          <div className="mt-1.5 flex justify-center gap-0.5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Star
                key={i}
                className={cn(
                  "h-4 w-4",
                  i < rounded ? "fill-amber-400 text-amber-400" : "text-border",
                )}
              />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          {dist.map((b) => (
            <div key={b.rating} className="flex items-center gap-2 text-xs">
              <span className="tnum flex w-6 items-center gap-0.5 text-muted-foreground">
                {b.rating}
                <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-700"
                  style={{ width: `${Math.round(b.ratio * 100)}%` }}
                />
              </div>
              <span className="tnum w-9 text-right text-subtle-foreground">
                {Math.round(b.ratio * 100)}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
