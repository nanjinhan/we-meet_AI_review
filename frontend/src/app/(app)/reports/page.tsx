import { FileText } from "lucide-react";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function ReportsPage() {
  return (
    <PagePlaceholder
      icon={FileText}
      title="주간 리포트"
      description="진단 색상 카드 · 처방 체크리스트"
      task="T-F5"
      api="GET /stores/{id}/reports/latest"
    />
  );
}
