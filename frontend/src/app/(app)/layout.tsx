"use client";

import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const NAV = [
  { href: "/dashboard", label: "대시보드" },
  { href: "/inbox", label: "인박스" },
  { href: "/reports", label: "리포트" },
  { href: "/compare", label: "비교" },
  { href: "/assistant", label: "비서" },
  { href: "/settings", label: "설정" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const logout = async () => {
    if (isSupabaseConfigured()) {
      await createClient().auth.signOut();
    }
    router.push("/login");
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <span className="font-bold">리뷰 진단 AI</span>
        <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-800">
          로그아웃
        </button>
      </header>

      <main className="flex-1 p-4">{children}</main>

      <nav className="sticky bottom-0 grid grid-cols-6 border-t bg-white text-center text-xs">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`py-2 ${active ? "font-semibold text-blue-600" : "text-gray-500"}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
