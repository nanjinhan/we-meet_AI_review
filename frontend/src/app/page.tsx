import { redirect } from "next/navigation";

export default function Home() {
  // 진입점 → 대시보드. 미로그인이면 middleware 가 /login 으로 보낸다.
  redirect("/dashboard");
}
