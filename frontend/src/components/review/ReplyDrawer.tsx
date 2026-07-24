"use client";

import { AnimatePresence, motion } from "motion/react";
import { ClipboardCheck, ExternalLink, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReviewItem } from "@/hooks/useReviews";
import { api, ApiError } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { cn } from "@/lib/utils";

type ReplyRead = components["schemas"]["ReplyRead"];
type Tone = "polite" | "friendly" | "apologetic";

const TONES: { value: Tone; label: string }[] = [
  { value: "polite", label: "정중하게" },
  { value: "friendly", label: "친근하게" },
  { value: "apologetic", label: "사과 톤" },
];

// 반자동 확정 사항: 서버는 네이버에 게시하지 않는다. 복사 후 스마트플레이스를 새 탭으로
// 열어 사장님이 직접 붙여넣는다 (CLAUDE.md 규칙 7). 리뷰별 딥링크는 채널 URL 확보 후 교체.
const SMARTPLACE_URL = "https://new.smartplace.naver.com/";

export function ReplyDrawer({
  review,
  onClose,
  onApproved,
}: {
  review: ReviewItem | null;
  onClose: () => void;
  onApproved: () => void;
}) {
  const [tone, setTone] = useState<Tone>("polite");
  const [reply, setReply] = useState<ReplyRead | null>(null);
  const [draft, setDraft] = useState("");
  const [generating, setGenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 드로어가 새 리뷰로 열릴 때 상태 초기화
  useEffect(() => {
    setTone("polite");
    setReply(null);
    setDraft(review?.reply_draft ?? "");
    setError(null);
    setCopied(false);
  }, [review?.id, review?.reply_draft]);

  const generate = async () => {
    if (!review) return;
    setGenerating(true);
    setError(null);
    try {
      const r = await api<ReplyRead>(`/reviews/${review.id}/reply:generate`, {
        method: "POST",
        body: JSON.stringify({ tone }),
      });
      setReply(r);
      setDraft(r.draft);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `초안 생성 실패 (${e.status}) — LLM 키/쿼터를 확인하세요.`
          : "초안 생성 중 오류가 났습니다.",
      );
    } finally {
      setGenerating(false);
    }
  };

  const copyOnly = async () => {
    await navigator.clipboard.writeText(draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const approve = async () => {
    if (!reply) return;
    setApproving(true);
    setError(null);
    try {
      await api<ReplyRead>(`/replies/${reply.id}:approve`, { method: "POST" });
      // 수정본을 복사한다 — 서버 저장본은 원본 초안, 게시는 사장님 손으로(반자동)
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      window.open(SMARTPLACE_URL, "_blank", "noopener");
      onApproved();
      setTimeout(onClose, 1200);
    } catch (e) {
      setError(
        e instanceof ApiError ? `승인 실패 (${e.status})` : "승인 중 오류가 났습니다.",
      );
    } finally {
      setApproving(false);
    }
  };

  return (
    <AnimatePresence>
      {review && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/40"
          />
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 320 }}
            className="fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-border bg-card p-5 shadow-xl"
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-bold">AI 답글</h2>
              <button
                onClick={onClose}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted"
                aria-label="닫기"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* 원문 리뷰 */}
            <div className="mb-4 rounded-lg bg-muted p-3 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{review.author_masked ?? "익명"}</span>{" "}
              {review.body}
            </div>

            {/* 톤 선택 + 생성 */}
            <div className="mb-3 flex flex-wrap items-center gap-2">
              {TONES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTone(t.value)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    tone === t.value
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-card text-muted-foreground hover:bg-muted",
                  )}
                >
                  {t.label}
                </button>
              ))}
              <Button size="sm" onClick={generate} disabled={generating} className="ml-auto">
                <Sparkles className="h-3.5 w-3.5" />
                {generating ? "생성 중…" : reply || draft ? "다시 생성" : "AI 초안 생성"}
              </Button>
            </div>

            {generating ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : (
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={5}
                placeholder="톤을 고르고 [AI 초안 생성]을 누르세요. 생성된 초안은 자유롭게 수정할 수 있습니다."
                className="w-full resize-y rounded-lg border border-input bg-background p-3 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            )}

            {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

            <div className="mt-4 flex items-center gap-2">
              {review.answered && !reply ? (
                // 이미 승인된 답글: 복사만 제공
                <Button variant="outline" onClick={copyOnly} disabled={!draft} className="flex-1">
                  <ClipboardCheck className="h-4 w-4" />
                  답글 복사
                </Button>
              ) : (
                <Button
                  onClick={approve}
                  disabled={!reply || approving || !draft.trim()}
                  className="flex-1"
                >
                  <ExternalLink className="h-4 w-4" />
                  {approving ? "승인 중…" : "승인하고 답글 달러 가기"}
                </Button>
              )}
            </div>
            <p className="mt-2 text-center text-[11px] text-subtle-foreground">
              승인하면 답글이 복사되고 스마트플레이스가 열립니다 — 붙여넣기만 하세요. (자동 게시 아님)
            </p>

            <AnimatePresence>
              {copied && (
                <motion.p
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mt-2 text-center text-xs font-medium text-delta-up"
                >
                  ✓ 복사됨 — 스마트플레이스에 붙여넣기만 하세요
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
