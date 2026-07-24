import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CompareAspect } from "@/hooks/useCompare";

function ratio(neg: number, total: number): number | null {
  return total > 0 ? Math.round((neg / total) * 100) : null;
}

function Delta({ ours, comp }: { ours: number | null; comp: number | null }) {
  if (ours == null || comp == null) {
    return <span className="text-subtle-foreground">—</span>;
  }
  const d = ours - comp; // 부정 비율은 낮을수록 좋다 → 양수면 우리가 나쁨
  if (d === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        <Minus className="h-3.5 w-3.5" />
        동일
      </span>
    );
  }
  const worse = d > 0;
  return (
    <span
      className={`inline-flex items-center gap-1 font-medium ${worse ? "text-delta-down" : "text-delta-up"}`}
    >
      {worse ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
      {worse ? "+" : ""}
      {d}%p {worse ? "열세" : "우세"}
    </span>
  );
}

/** 차트와 같은 수치를 표로도 제공 — 색에만 의존하지 않는 접근성 경로. */
export function CompareTable({ aspects }: { aspects: CompareAspect[] }) {
  const rows = aspects.filter((a) => a.ours_total > 0 || a.comp_total > 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>수치로 보기</CardTitle>
      </CardHeader>
      <CardContent className="pt-3">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="pb-2 font-medium">항목</th>
                <th className="pb-2 text-right font-medium">우리 (언급)</th>
                <th className="pb-2 text-right font-medium">경쟁 (언급)</th>
                <th className="pb-2 text-right font-medium">격차</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((a) => {
                const ours = ratio(a.ours_neg, a.ours_total);
                const comp = ratio(a.comp_neg, a.comp_total);
                return (
                  <tr key={a.aspect} className="border-b border-border last:border-0">
                    <td className="py-2.5 font-medium">{a.aspect}</td>
                    <td className="py-2.5 text-right">
                      {ours == null ? "—" : `${ours}%`}
                      <span className="ml-1 text-xs text-subtle-foreground">({a.ours_total})</span>
                    </td>
                    <td className="py-2.5 text-right">
                      {comp == null ? "—" : `${comp}%`}
                      <span className="ml-1 text-xs text-subtle-foreground">({a.comp_total})</span>
                    </td>
                    <td className="py-2.5 text-right text-xs">
                      <Delta ours={ours} comp={comp} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
