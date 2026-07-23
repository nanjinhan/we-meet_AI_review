import { Rocket } from "lucide-react";
import { PagePlaceholder } from "@/components/page-placeholder";

export default function OnboardingPage() {
  return (
    <PagePlaceholder
      icon={Rocket}
      title="온보딩"
      description="매장 등록 → 네이버 URL → 경쟁매장 → 톤 프로필 → 알림 동의"
      task="T-F2"
      api="POST /stores"
    />
  );
}
