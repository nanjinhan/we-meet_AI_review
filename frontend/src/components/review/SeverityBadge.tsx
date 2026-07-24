import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

const LABELS: Record<string, string> = {
  normal: "일반",
  uncomfortable: "불편",
  complaint: "컴플레인",
  malicious: "악성",
};

/** 리뷰 심각도 뱃지 — urgent 는 빨강 강조 (FRONTEND.md §4). */
export function SeverityBadge({ severity, urgent }: { severity: string | null; urgent: boolean }) {
  if (urgent) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-semibold text-destructive">
        <AlertTriangle className="h-3 w-3" />
        긴급
      </span>
    );
  }
  if (!severity || severity === "normal") return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        severity === "uncomfortable" && "bg-muted text-muted-foreground",
        (severity === "complaint" || severity === "malicious") &&
          "bg-destructive/10 text-destructive",
      )}
    >
      {LABELS[severity] ?? severity}
    </span>
  );
}
