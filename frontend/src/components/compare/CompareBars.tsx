"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CompareAspect } from "@/hooks/useCompare";

const OURS = "var(--chart-ours)";
const COMP = "var(--chart-comp)";

/** 부정 비율(%) — 인사이트 문구와 같은 기준이라 화면과 설명이 어긋나지 않는다. */
function negRatio(neg: number, total: number): number {
  return total > 0 ? Math.round((neg / total) * 100) : 0;
}

export function CompareBars({ aspects }: { aspects: CompareAspect[] }) {
  const data = aspects
    .filter((a) => a.ours_total > 0 || a.comp_total > 0)
    .map((a) => ({
      aspect: a.aspect,
      "우리 매장": negRatio(a.ours_neg, a.ours_total),
      "경쟁 매장": negRatio(a.comp_neg, a.comp_total),
    }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>항목별 부정 비율</CardTitle>
        <p className="text-xs text-muted-foreground">낮을수록 좋습니다 (해당 항목 언급 중 부정 비중)</p>
      </CardHeader>
      <CardContent className="h-80 pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
            barGap={2}
          >
            <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 100]}
              unit="%"
              tick={{ fontSize: 11, fill: "var(--chart-axis)" }}
              axisLine={{ stroke: "var(--chart-grid)" }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="aspect"
              width={64}
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: "var(--muted)" }}
              formatter={(v) => `${v ?? 0}%`}
              contentStyle={{
                borderRadius: 10,
                border: "1px solid var(--border)",
                background: "var(--card)",
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="우리 매장" fill={OURS} radius={[0, 4, 4, 0]} barSize={10} />
            <Bar dataKey="경쟁 매장" fill={COMP} radius={[0, 4, 4, 0]} barSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
