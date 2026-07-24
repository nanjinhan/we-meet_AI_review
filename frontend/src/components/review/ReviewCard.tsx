"use client";

import { CheckCircle2, Star } from "lucide-react";
import { SeverityBadge } from "@/components/review/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ReviewItem } from "@/hooks/useReviews";
import { cn } from "@/lib/utils";

function Stars({ rating }: { rating: number | null }) {
  if (rating == null) return null;
  return (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={cn(
            "h-3.5 w-3.5",
            i < rating ? "fill-amber-400 text-amber-400" : "text-border",
          )}
        />
      ))}
    </span>
  );
}

export function ReviewCard({ review, onClick }: { review: ReviewItem; onClick: () => void }) {
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      className="cursor-pointer transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <CardContent className="space-y-2 p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold">{review.author_masked ?? "익명"}</span>
          <Stars rating={review.rating} />
          <span className="text-xs text-subtle-foreground">{review.written_at ?? ""}</span>
          <span className="ml-auto flex items-center gap-1.5">
            <SeverityBadge severity={review.severity} urgent={review.urgent} />
            {review.answered && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-accent-foreground">
                <CheckCircle2 className="h-3 w-3" />
                답변됨
              </span>
            )}
          </span>
        </div>

        <p className="text-sm leading-relaxed">{review.body}</p>

        {review.aspects.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {review.aspects.map((a, i) => {
              const aspect = a as { category?: string; polarity?: string };
              return (
                <Badge
                  key={i}
                  variant="secondary"
                  className={cn(
                    aspect.polarity === "neg" && "bg-destructive/10 text-destructive",
                    aspect.polarity === "pos" && "bg-accent text-accent-foreground",
                  )}
                >
                  {aspect.category}
                </Badge>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
