import { Card, CardContent } from "@/components/ui/card";
import type { Diagnosis } from "@/hooks/useReport";

/**
 * 진단 카드 — 레퍼런스(cascal "What Customers Like")의 번호 + 컬러 알약 배지 방식.
 * 아이콘/세로 바 없이, 색만으로 의미를 전달하지 않도록 배지에 레벨 이름을 적는다.
 */
const LEVELS: Record<string, { label: string; pill: string; num: string }> = {
  crit: {
    label: "심각",
    pill: "bg-level-crit/10 text-level-crit",
    num: "bg-level-crit/10 text-level-crit",
  },
  warn: {
    label: "주의",
    pill: "bg-level-warn/15 text-amber-700",
    num: "bg-level-warn/15 text-amber-700",
  },
  strength: {
    label: "강점",
    pill: "bg-level-strength/10 text-level-strength",
    num: "bg-level-strength/10 text-level-strength",
  },
  opportunity: {
    label: "기회",
    pill: "bg-level-opportunity/10 text-level-opportunity",
    num: "bg-level-opportunity/10 text-level-opportunity",
  },
};

export function DiagnosisCard({ item, index }: { item: Diagnosis; index: number }) {
  const level = LEVELS[item.level] ?? LEVELS.opportunity;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <span
            className={`tnum flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${level.num}`}
          >
            {index + 1}
          </span>
          <p className="min-w-0 flex-1 truncate text-sm font-semibold">{item.title}</p>
          <span
            className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${level.pill}`}
          >
            {level.label}
          </span>
        </div>
        <p className="mt-2 pl-9 text-xs leading-relaxed text-muted-foreground">
          <span className="text-subtle-foreground">근거 · </span>
          {item.evidence}
        </p>
      </CardContent>
    </Card>
  );
}
