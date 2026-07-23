import { Scale } from "lucide-react";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function ComparePage() {
  return (
    <PagePlaceholder
      icon={Scale}
      title="경쟁매장 비교"
      description="항목별 우리 vs 경쟁 비교 + 한 줄 인사이트"
      task="T-F5"
      api="GET /stores/{id}/compare"
    />
  );
}
