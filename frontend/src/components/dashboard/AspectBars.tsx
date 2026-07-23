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
import type { Dashboard } from "@/hooks/useDashboard";

const POS = "var(--chart-pos)";
const NEG = "var(--chart-neg)";

export function AspectBars({ aspects }: { aspects: Dashboard["aspects"] }) {
  const data = aspects.map((a) => ({ aspect: a.aspect, 긍정: a.pos_cnt, 부정: a.neg_cnt }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>항목별 긍정 / 부정</CardTitle>
      </CardHeader>
      <CardContent className="h-64 pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
            barGap={2}
          >
            <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
            <XAxis
              type="number"
              allowDecimals={false}
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
              contentStyle={{
                borderRadius: 10,
                border: "1px solid var(--border)",
                background: "var(--card)",
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="긍정" fill={POS} radius={[0, 4, 4, 0]} barSize={10} />
            <Bar dataKey="부정" fill={NEG} radius={[0, 4, 4, 0]} barSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
