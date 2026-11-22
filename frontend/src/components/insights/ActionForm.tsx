"use client";

import { Check, Target } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCreateAction } from "@/hooks/useActions";
import { aspectCopy, type Polarity, todayIso } from "@/lib/insight-copy";

/**
 * 실행 과제 기록 — 근거를 본 뒤 "이번 주에 실행할 행동 하나"와 실행일을 남긴다.
 * 후보 칩은 입력을 돕는 예시일 뿐 처방이 아니다. 무엇을 할지는 점주가 정한다.
 */
export function ActionForm({
  storeId,
  aspect,
  polarity,
}: {
  storeId: number;
  aspect: string;
  polarity: Polarity;
}) {
  const [title, setTitle] = useState("");
  const [startedOn, setStartedOn] = useState(todayIso());
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const create = useCreateAction(storeId);
  const ideas = aspectCopy(aspect, polarity).ideas;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !startedOn) return;
    create.mutate(
      { aspect, polarity, title: title.trim(), started_on: startedOn, note: note.trim() || null },
      {
        onSuccess: () => {
          setTitle("");
          setNote("");
          setSaved(true);
        },
      },
    );
  };

  return (
    <form onSubmit={submit} className="space-y-2.5 rounded-xl border border-border bg-accent/50 p-3.5">
      <div className="flex items-center gap-1.5">
        <Target className="h-4 w-4 text-primary" />
        <p className="text-sm font-semibold">이번 주에 실행할 행동 하나</p>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        위 근거가 실제 매장 상황과 맞는지 먼저 확인한 뒤, 해볼 일을 하나만 적어 두세요. 실행일
        이후의 리뷰에서 같은 항목이 어떻게 나타나는지 이어서 보여드립니다.
      </p>

      <div className="flex flex-wrap gap-1.5">
        {ideas.map((idea) => (
          <button
            key={idea}
            type="button"
            onClick={() => {
              setTitle(idea);
              setSaved(false);
            }}
            className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary hover:text-primary"
          >
            {idea}
          </button>
        ))}
      </div>

      <input
        value={title}
        onChange={(e) => {
          setTitle(e.target.value);
          setSaved(false);
        }}
        maxLength={120}
        placeholder="예) 예상 대기시간 안내 개선"
        aria-label="실행할 행동"
        className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          실행일
          <input
            type="date"
            value={startedOn}
            onChange={(e) => setStartedOn(e.target.value)}
            className="tnum rounded-lg border border-input bg-card px-2 py-1.5 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
          placeholder="메모 (선택)"
          aria-label="메모"
          className="min-w-40 flex-1 rounded-lg border border-input bg-card px-3 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" size="sm" disabled={create.isPending || !title.trim() || !startedOn}>
          {create.isPending ? "저장 중…" : "기록하기"}
        </Button>
      </div>

      {create.isError && (
        <p className="text-xs text-destructive">저장하지 못했습니다. 다시 시도해 주세요.</p>
      )}
      {saved && (
        <p className="flex items-center gap-1 text-xs font-medium text-delta-up">
          <Check className="h-3.5 w-3.5" />
          기록했습니다. 근거 진단 화면의 ‘실행 과제’에서 이후 리뷰를 함께 볼 수 있어요.
        </p>
      )}
    </form>
  );
}
