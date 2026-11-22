import { Database } from "lucide-react";
import { SUFFICIENCY, type SufficiencyLevel } from "@/lib/insight-copy";
import { cn } from "@/lib/utils";

/**
 * 자료 충분도 뱃지 — 점수(만족도)와 따로 표시한다.
 * 등급 이름만 보여주고 % 로 바꾸지 않는다. 실제 건수는 항상 옆에 함께 적는다(호출부 책임).
 */
export function SufficiencyBadge({
  level,
  className,
}: {
  level: SufficiencyLevel;
  className?: string;
}) {
  const s = SUFFICIENCY[level];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold",
        s.tone,
        className,
      )}
    >
      <Database className="h-3 w-3" />
      {s.label}
    </span>
  );
}
