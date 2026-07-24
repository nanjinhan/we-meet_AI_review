import { AlertOctagon, AlertTriangle, Lightbulb, ThumbsUp, type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Diagnosis } from "@/hooks/useReport";

/** 진단 레벨별 표현. 색만으로 의미를 전달하지 않도록 아이콘+라벨을 함께 쓴다. */
const LEVELS: Record<string, { label: string; icon: LucideIcon; fg: string; bg: string }> = {
  crit: {
    label: "심각",
    icon: AlertOctagon,
    fg: "text-level-crit",
    bg: "bg-level-crit/10",
  },
  warn: {
    label: "주의",
    icon: AlertTriangle,
    fg: "text-amber-700",
    bg: "bg-level-warn/15",
  },
  strength: {
    label: "강점",
    icon: ThumbsUp,
    fg: "text-level-strength",
    bg: "bg-level-strength/10",
  },
  opportunity: {
    label: "기회",
    icon: Lightbulb,
    fg: "text-level-opportunity",
    bg: "bg-level-opportunity/10",
  },
};

export function DiagnosisCard({ item }: { item: Diagnosis }) {
  const level = LEVELS[item.level] ?? LEVELS.opportunity;
  const Icon = level.icon;

  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${level.bg} ${level.fg}`}
        >
          <Icon className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 space-y-1.5">
          <p className={`text-[11px] font-semibold ${level.fg}`}>{level.label}</p>
          <p className="text-sm font-semibold leading-snug">{item.title}</p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            <span className="text-subtle-foreground">근거 · </span>
            {item.evidence}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
