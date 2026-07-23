import { Inbox } from "lucide-react";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function InboxPage() {
  return (
    <PagePlaceholder
      icon={Inbox}
      title="리뷰 인박스"
      description="필터 · 무한스크롤 · AI 답글 드로어"
      task="T-F3"
      api="GET /stores/{id}/reviews"
    />
  );
}
