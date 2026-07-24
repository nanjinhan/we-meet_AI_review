"use client";

import {
  Bot,
  FileText,
  Inbox,
  LayoutDashboard,
  LogOut,
  Scale,
  Settings,
  Sparkles,
  Store as StoreIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { StoreProvider, useStore } from "@/components/store-provider";
import { cn } from "@/lib/utils";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

const NAV = [
  { href: "/dashboard", label: "대시보드", icon: LayoutDashboard },
  { href: "/inbox", label: "인박스", icon: Inbox },
  { href: "/reports", label: "리포트", icon: FileText },
  { href: "/compare", label: "비교", icon: Scale },
  { href: "/assistant", label: "AI 비서", icon: Bot },
  { href: "/settings", label: "설정", icon: Settings },
];

function StoreSelect() {
  const { stores, store, setStoreId } = useStore();
  const router = useRouter();
  if (stores.length === 0) {
    return (
      <Link
        href="/onboarding"
        className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        <StoreIcon className="h-4 w-4" />
        매장 등록하기
      </Link>
    );
  }
  return (
    <label className="flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm">
      <StoreIcon className="h-4 w-4 text-muted-foreground" />
      <select
        value={store?.id ?? ""}
        onChange={(e) => {
          if (e.target.value === "__add__") {
            router.push("/onboarding");
            return;
          }
          setStoreId(Number(e.target.value));
        }}
        className="max-w-40 bg-transparent outline-none"
      >
        {stores.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
        <option value="__add__">＋ 매장 추가</option>
      </select>
    </label>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const logout = async () => {
    if (isSupabaseConfigured()) {
      await createClient().auth.signOut();
    }
    router.push("/login");
  };

  return (
    <div className="min-h-screen md:flex">
      {/* 데스크톱 사이드바 — 밝은 배경 + 바이올렛 활성 (레퍼런스: cascal) */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-border bg-card md:flex">
        <div className="flex items-center gap-2.5 px-5 py-6">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles className="h-4.5 w-4.5" />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-bold">리뷰 진단 AI</p>
            <p className="text-[11px] text-subtle-foreground">Naver Place Insights</p>
          </div>
        </div>

        <p className="px-6 pb-2 text-[10px] font-semibold tracking-widest text-subtle-foreground">
          MAIN MENU
        </p>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                  active
                    ? "bg-accent font-semibold text-accent-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <Icon className={cn("h-4 w-4", active && "text-primary")} />
                {label}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={logout}
          className="mx-3 mb-5 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          로그아웃
        </button>
      </aside>

      <div className="flex min-h-screen flex-1 flex-col md:pl-60">
        {/* 상단 헤더 */}
        <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border bg-card/90 px-4 py-3 backdrop-blur md:px-8">
          <span className="font-bold md:hidden">리뷰 진단 AI</span>
          <div className="ml-auto flex items-center gap-2">
            <StoreSelect />
            <button
              onClick={logout}
              className="rounded-lg p-2 text-muted-foreground hover:bg-muted md:hidden"
              aria-label="로그아웃"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 pb-24 md:px-8 md:pb-8">
          <div className="mx-auto w-full max-w-5xl">{children}</div>
        </main>

        {/* 모바일 하단 탭 */}
        <nav className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-6 border-t border-border bg-card/95 text-center backdrop-blur md:hidden">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex flex-col items-center gap-0.5 py-2 text-[10px]",
                  active ? "font-semibold text-primary" : "text-muted-foreground",
                )}
              >
                <Icon className="h-5 w-5" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <StoreProvider>
      <Shell>{children}</Shell>
    </StoreProvider>
  );
}
