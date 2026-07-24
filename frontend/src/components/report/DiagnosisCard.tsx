import { AlertOctagon, AlertTriangle, Lightbulb, ThumbsUp, type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Diagnosis } from "@/hooks/useReport";

/** 진단 레벨별 표현. 색만으로 의미를 전달하지 않도록 아이콘+라벨을 함께 쓴다. */
const LEVELS: Record<string, { label: string; icon: LucideIcon; bar: string; fg: string; bg: string }> =
  {
    crit: {
      label: "심각",
      icon: AlertOctagon,
      bar: "bg-level-crit",
      fg: "text-level-crit",
      bg: "bg-level-crit/10",
    },
    warn: {
      label: "주의",
      icon: AlertTriangle,
      bar: "bg-level-warn",
      fg: "text-amber-700",
      bg: "bg-level-warn/15",
    },
    strength: {
      label: "강점",
      icon: ThumbsUp,
      bar: "bg-level-strength",
      fg: "text-level-strength",
      bg: "bg-level-strength/10",
    },
    opportunity: {
      label: "기회",
      icon: Lightbulb,
      bar: "bg-level-opportunity",
      fg: "text-level-opportunity",
      bg: "bg-level-opportunity/10",
    },
  };

export function DiagnosisCard({ item }: { item: Diagnosis }) {
  const level = LEVELS[item.level] ?? LEVELS.opportunity;
  const Icon = level.icon;

  return (
    <Card className="relative overflow-hidden">
      {/* 좌측 컬러 바 — 레벨 구분의 보조 단서 */}
      <span className={`absolute inset-y-0 left-0 w-1 ${level.bar}`} />
      <CardContent className="space-y-2 p-4 pl-5">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${level.bg} ${level.fg}`}
          >
            <Icon className="h-3.5 w-3.5" />
            {level.label}
          </span>
        </div>
        <p className="text-sm font-semibold">{item.title}</p>
        <p className="rounded-lg bg-muted px-3 py-2 text-xs leading-relaxed text-muted-foreground">
          근거 · {item.evidence}
        </p>
      </CardContent>
    </Card>
  );
}
