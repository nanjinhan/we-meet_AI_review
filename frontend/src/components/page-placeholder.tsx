import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

/** 아직 구현 전인 화면의 공통 자리표시자 — 제목 + 예정 태스크 + 사용할 API. */
export function PagePlaceholder({
  icon: Icon,
  title,
  description,
  task,
  api,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  task: string;
  api: string;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent text-accent-foreground">
            <Icon className="h-6 w-6" />
          </span>
          <p className="text-sm font-medium">준비 중인 화면입니다</p>
          <p className="text-xs text-muted-foreground">
            <Badge variant="secondary">{task}</Badge>
            <span className="ml-2">
              API: <code className="rounded bg-muted px-1 py-0.5">{api}</code>
            </span>
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
