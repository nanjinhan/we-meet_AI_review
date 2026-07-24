"use client";

import { MessageSquare, ReplyAll, Smile, Star } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Dashboard } from "@/hooks/useDashboard";

/** Stripe 풍 지표 타일 — 라벨(작고 흐리게) 위, 값(크고 정밀하게) 아래. */
export function StatTiles({ data }: { data: Dashboard }) {
  const tiles = [
    {
      icon: MessageSquare,
      label: "리뷰",
      value: data.total_reviews.toLocaleString("ko-KR"),
      unit: "건",
    },
    {
      icon: Smile,
      label: "긍정 비율",
      value: `${Math.round(data.positive_ratio * 100)}`,
      unit: "%",
    },
    {
      icon: Star,
      label: "평균 별점",
      value: data.avg_rating != null ? data.avg_rating.toFixed(1) : "—",
      unit: data.avg_rating != null ? "/ 5" : "",
    },
    {
      icon: ReplyAll,
      label: "답변율",
      value: `${Math.round(data.answer_rate * 100)}`,
      unit: "%",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map(({ icon: Icon, label, value, unit }) => (
        <Card key={label}>
          <CardContent className="space-y-1.5 p-4">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Icon className="h-3.5 w-3.5 text-subtle-foreground" />
              {label}
            </p>
            <p className="tnum text-2xl font-semibold tracking-tight">
              {value}
              {unit && (
                <span className="ml-1 text-sm font-normal text-subtle-foreground">{unit}</span>
              )}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
