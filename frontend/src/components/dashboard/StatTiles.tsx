"use client";

import { MessageSquare, ReplyAll, Smile, Star } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Dashboard } from "@/hooks/useDashboard";

export function StatTiles({ data }: { data: Dashboard }) {
  const tiles = [
    {
      icon: MessageSquare,
      label: "리뷰 수",
      value: data.total_reviews.toLocaleString("ko-KR"),
    },
    {
      icon: Smile,
      label: "긍정 비율",
      value: `${Math.round(data.positive_ratio * 100)}%`,
    },
    {
      icon: Star,
      label: "평균 별점",
      value: data.avg_rating != null ? data.avg_rating.toFixed(1) : "—",
    },
    {
      icon: ReplyAll,
      label: "답변율",
      value: `${Math.round(data.answer_rate * 100)}%`,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map(({ icon: Icon, label, value }) => (
        <Card key={label}>
          <CardContent className="flex items-center gap-3 p-4">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <Icon className="h-4 w-4" />
            </span>
            <div className="leading-tight">
              <p className="text-lg font-bold">{value}</p>
              <p className="text-xs text-muted-foreground">{label}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
