import { Settings } from "lucide-react";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function SettingsPage() {
  return (
    <PagePlaceholder
      icon={Settings}
      title="설정"
      description="톤 프로필 · 알림 설정"
      task="T-F 이후"
      api="PUT /stores/{id}/settings"
    />
  );
}
