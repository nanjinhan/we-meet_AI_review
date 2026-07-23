import { Bot } from "lucide-react";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function AssistantPage() {
  return (
    <PagePlaceholder
      icon={Bot}
      title="AI 비서"
      description="매장 데이터 기반 질의응답 채팅 (SSE 스트리밍)"
      task="T-F7"
      api="POST /stores/{id}/assistant/messages"
    />
  );
}
