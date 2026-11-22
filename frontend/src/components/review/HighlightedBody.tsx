import { cn } from "@/lib/utils";

export type Highlight = { text: string; polarity?: string | null };

/**
 * 리뷰 본문에서 근거 문장을 표시한다. 근거 문장은 서버가 원문 대조를 마친 '본문의 연속 구간'이라
 * 그대로 찾아 칠하면 된다 — 못 찾으면(예전 분석 등) 조용히 본문만 보여준다.
 */
const DEFAULT_TONES = { neg: "bg-chart-neg/15", pos: "bg-chart-pos/15" };

export function HighlightedBody({
  body,
  highlights,
  className,
  tones = DEFAULT_TONES,
}: {
  body: string;
  highlights: Highlight[];
  className?: string;
  /** 방향별 배경색 클래스 — 화면의 다른 표시(태그·막대)와 색을 맞출 때 지정 */
  tones?: { neg: string; pos: string };
}) {
  const ranges = highlights
    .filter((h) => h.text)
    .map((h) => {
      const start = body.indexOf(h.text);
      return { start, end: start + h.text.length, polarity: h.polarity };
    })
    .filter((r) => r.start >= 0)
    .sort((a, b) => a.start - b.start);

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const r of ranges) {
    if (r.start < cursor) continue; // 겹치는 구간은 앞의 것만
    if (r.start > cursor) parts.push(body.slice(cursor, r.start));
    parts.push(
      <mark
        key={r.start}
        className={cn(
          "rounded px-0.5 py-px font-medium text-foreground",
          r.polarity === "pos" ? tones.pos : tones.neg,
        )}
      >
        {body.slice(r.start, r.end)}
      </mark>,
    );
    cursor = r.end;
  }
  if (cursor < body.length) parts.push(body.slice(cursor));

  return <p className={cn("text-sm leading-relaxed", className)}>{parts}</p>;
}
