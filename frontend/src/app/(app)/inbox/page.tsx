"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Inbox as InboxIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { ReplyDrawer } from "@/components/review/ReplyDrawer";
import { ReviewCard } from "@/components/review/ReviewCard";
import { useStore } from "@/components/store-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useReviews, type InboxFilter, type ReviewItem } from "@/hooks/useReviews";
import { cn } from "@/lib/utils";

const FILTERS: { value: InboxFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "neg", label: "부정" },
  { value: "urgent", label: "긴급" },
  { value: "unanswered", label: "미답변" },
];

function InboxContent() {
  const { store, isLoading: storeLoading } = useStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const raw = searchParams.get("filter");
  const filter: InboxFilter = FILTERS.some((f) => f.value === raw)
    ? (raw as InboxFilter)
    : "all";

  const { data, isLoading, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useReviews(store?.id, filter);
  const [selected, setSelected] = useState<ReviewItem | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const setFilter = (f: InboxFilter) => {
    router.replace(f === "all" ? "/inbox" : `/inbox?filter=${f}`, { scroll: false });
  };

  // 무한스크롤: 목록 끝 sentinel 이 보이면 다음 페이지
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  const items = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">리뷰 인박스</h1>
        <p className="text-sm text-muted-foreground">
          {store ? `${store.name}의 리뷰를 확인하고 AI 답글을 달아보세요` : "리뷰 관리"}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors",
              filter === f.value
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-card text-muted-foreground hover:bg-muted",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {(storeLoading || isLoading) && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {isError && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            리뷰를 불러오지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
            <InboxIcon className="h-8 w-8 text-subtle-foreground" />
            <p className="text-sm text-muted-foreground">이 조건에 맞는 리뷰가 없습니다.</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {items.map((r) => (
          <ReviewCard key={r.id} review={r} onClick={() => setSelected(r)} />
        ))}
      </div>

      <div ref={sentinelRef} />
      {isFetchingNextPage && <Skeleton className="h-28" />}
      {hasNextPage && !isFetchingNextPage && (
        <div className="text-center">
          <Button variant="outline" size="sm" onClick={() => fetchNextPage()}>
            더 보기
          </Button>
        </div>
      )}

      <ReplyDrawer
        review={selected}
        onClose={() => setSelected(null)}
        onApproved={() => queryClient.invalidateQueries({ queryKey: ["reviews", store?.id] })}
      />
    </section>
  );
}

export default function InboxPage() {
  // useSearchParams 는 Suspense 경계가 필요 (Next.js App Router)
  return (
    <Suspense>
      <InboxContent />
    </Suspense>
  );
}
