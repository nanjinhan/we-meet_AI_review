"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Bell, Check, Link2, MessageSquareQuote, Store, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useStore } from "@/components/store-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { cn } from "@/lib/utils";

type StoreOut = components["schemas"]["StoreOut"];

const CATEGORIES = ["음식점", "카페", "미용실", "옷가게·리테일", "병원·의원", "기타"];

const STEPS = [
  { icon: Store, label: "매장 정보" },
  { icon: Link2, label: "리뷰 채널" },
  { icon: Users, label: "경쟁매장" },
  { icon: MessageSquareQuote, label: "답글 톤" },
  { icon: Bell, label: "알림" },
];

const inputCls =
  "w-full rounded-lg border border-input bg-card px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { setStoreId } = useStore();

  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // step 1
  const [name, setName] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [address, setAddress] = useState("");
  const [createdStore, setCreatedStore] = useState<StoreOut | null>(null);
  // step 2
  const [placeUrl, setPlaceUrl] = useState("");
  // step 3
  const [competitors, setCompetitors] = useState([{ name: "", url: "" }]);
  // step 4
  const [tone, setTone] = useState<"polite" | "friendly" | "apologetic">("polite");
  const [examples, setExamples] = useState(["", "", ""]);
  // step 5
  const [notifyUrgent, setNotifyUrgent] = useState(true);
  const [notifyDigest, setNotifyDigest] = useState(true);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setStep((s) => s + 1);
    } catch {
      setError("저장에 실패했어요. 백엔드가 실행 중인지 확인하고 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  };

  const submitStore = () =>
    run(async () => {
      // 뒤로 갔다 다시 오면 중복 생성 방지 — 이미 만든 매장 재사용
      if (!createdStore) {
        const store = await api<StoreOut>("/stores", {
          method: "POST",
          body: JSON.stringify({ name, category, address: address || null }),
        });
        setCreatedStore(store);
      }
    });

  const submitChannel = () =>
    run(async () => {
      if (placeUrl.trim() && createdStore) {
        await api(`/stores/${createdStore.id}/channels`, {
          method: "POST",
          body: JSON.stringify({ platform: "naver", external_url: placeUrl.trim() }),
        });
      }
    });

  const submitCompetitors = () =>
    run(async () => {
      if (!createdStore) return;
      for (const c of competitors) {
        if (c.name.trim() && c.url.trim()) {
          await api(`/stores/${createdStore.id}/competitors`, {
            method: "POST",
            body: JSON.stringify({ name: c.name.trim(), external_url: c.url.trim() }),
          });
        }
      }
    });

  const submitTone = () =>
    run(async () => {
      if (!createdStore) return;
      const tone_examples = examples.map((e) => e.trim()).filter(Boolean);
      await api(`/stores/${createdStore.id}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          default_tone: tone,
          ...(tone_examples.length > 0 ? { tone_examples } : {}),
        }),
      });
    });

  const finish = async () => {
    setBusy(true);
    setError(null);
    try {
      if (createdStore) {
        await api(`/stores/${createdStore.id}/settings`, {
          method: "PUT",
          body: JSON.stringify({ notify_urgent: notifyUrgent, notify_digest: notifyDigest }),
        });
        await queryClient.invalidateQueries({ queryKey: ["stores"] });
        setStoreId(createdStore.id);
      }
      router.push("/dashboard");
    } catch {
      setError("저장에 실패했어요. 다시 시도해 주세요.");
      setBusy(false);
    }
  };

  return (
    <section className="mx-auto max-w-xl space-y-5">
      <div>
        <h1 className="text-xl font-bold">매장 등록</h1>
        <p className="text-sm text-muted-foreground">
          5단계면 끝나요. 채널·경쟁매장은 나중에 추가해도 됩니다.
        </p>
      </div>

      {/* 스텝 인디케이터 */}
      <ol className="flex items-center gap-1">
        {STEPS.map(({ icon: Icon, label }, i) => (
          <li key={label} className="flex flex-1 flex-col items-center gap-1">
            <span
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full border text-xs transition-colors",
                i < step && "border-primary bg-primary text-primary-foreground",
                i === step && "border-primary bg-accent text-accent-foreground",
                i > step && "border-border bg-card text-subtle-foreground",
              )}
            >
              {i < step ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
            </span>
            <span
              className={cn(
                "text-[10px]",
                i === step ? "font-semibold text-foreground" : "text-subtle-foreground",
              )}
            >
              {label}
            </span>
          </li>
        ))}
      </ol>

      <Card>
        <CardContent className="space-y-4">
          {step === 0 && (
            <>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">매장 이름 *</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="예: 성수 브런치카페 온도"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">업종</label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c}
                      onClick={() => setCategory(c)}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                        category === c
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-card text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {c}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-subtle-foreground">
                  음식점·카페 외 업종은 분석 항목이 아직 음식점 기준이에요 (개선 예정).
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">주소 (선택)</label>
                <input
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="예: 서울 성동구 성수동 12-3"
                  className={inputCls}
                />
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  네이버 플레이스 URL (선택)
                </label>
                <input
                  value={placeUrl}
                  onChange={(e) => setPlaceUrl(e.target.value)}
                  placeholder="https://map.naver.com/p/entry/place/..."
                  className={inputCls}
                />
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                등록하면 첫 수집이 자동으로 예약됩니다. URL이 없거나 나중에 하려면 건너뛰어도
                돼요 — 설정에서 CSV 업로드로도 리뷰를 넣을 수 있습니다.
              </p>
            </>
          )}

          {step === 2 && (
            <>
              <p className="text-xs leading-relaxed text-muted-foreground">
                비교하고 싶은 경쟁매장을 2~3개 등록하면 &ldquo;비교&rdquo; 화면이 살아납니다.
                (선택 — 건너뛰기 가능)
              </p>
              {competitors.map((c, i) => (
                <div key={i} className="grid grid-cols-5 gap-2">
                  <input
                    value={c.name}
                    onChange={(e) =>
                      setCompetitors((prev) =>
                        prev.map((p, j) => (j === i ? { ...p, name: e.target.value } : p)),
                      )
                    }
                    placeholder="매장 이름"
                    className={cn(inputCls, "col-span-2")}
                  />
                  <input
                    value={c.url}
                    onChange={(e) =>
                      setCompetitors((prev) =>
                        prev.map((p, j) => (j === i ? { ...p, url: e.target.value } : p)),
                      )
                    }
                    placeholder="네이버 플레이스 URL"
                    className={cn(inputCls, "col-span-3")}
                  />
                </div>
              ))}
              {competitors.length < 3 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCompetitors((prev) => [...prev, { name: "", url: "" }])}
                >
                  + 경쟁매장 추가
                </Button>
              )}
            </>
          )}

          {step === 3 && (
            <>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">기본 답글 톤</label>
                <div className="flex gap-2">
                  {(
                    [
                      ["polite", "정중하게"],
                      ["friendly", "친근하게"],
                      ["apologetic", "사과 톤"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      onClick={() => setTone(value)}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                        tone === value
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-card text-muted-foreground hover:bg-muted",
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  평소 쓰시는 답글 예시 (선택, AI가 말투를 배워요)
                </label>
                {examples.map((ex, i) => (
                  <textarea
                    key={i}
                    value={ex}
                    onChange={(e) =>
                      setExamples((prev) => prev.map((p, j) => (j === i ? e.target.value : p)))
                    }
                    rows={2}
                    placeholder={`예시 답글 ${i + 1}`}
                    className={cn(inputCls, "resize-none")}
                  />
                ))}
              </div>
            </>
          )}

          {step === 4 && (
            <div className="space-y-3">
              {(
                [
                  ["긴급 리뷰 알림", "1~2점·악성 리뷰가 오면 바로 알려드려요", notifyUrgent, setNotifyUrgent],
                  ["부정 리뷰 요약", "일반 부정 리뷰를 모아서 알려드려요", notifyDigest, setNotifyDigest],
                ] as const
              ).map(([title, desc, value, setter]) => (
                <button
                  key={title}
                  onClick={() => setter(!value)}
                  className="flex w-full items-center justify-between rounded-lg border border-border p-3 text-left transition-colors hover:bg-muted"
                >
                  <span>
                    <span className="block text-sm font-medium">{title}</span>
                    <span className="block text-xs text-muted-foreground">{desc}</span>
                  </span>
                  <span
                    className={cn(
                      "relative h-6 w-11 shrink-0 rounded-full transition-colors",
                      value ? "bg-primary" : "bg-muted",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
                        value ? "left-[22px]" : "left-0.5",
                      )}
                    />
                  </span>
                </button>
              ))}
              <p className="text-[11px] text-subtle-foreground">
                카카오톡·웹푸시 실제 발송 연결은 준비 중이에요. 지금은 수신 설정만 저장됩니다.
              </p>
            </div>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}

          <div className="flex items-center justify-between pt-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0 || busy}
            >
              <ArrowLeft className="h-4 w-4" />
              이전
            </Button>
            {step === 0 && (
              <Button onClick={submitStore} disabled={busy || !name.trim()}>
                {busy ? "저장 중…" : "다음"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
            {step === 1 && (
              <Button onClick={submitChannel} disabled={busy}>
                {busy ? "저장 중…" : placeUrl.trim() ? "다음" : "건너뛰기"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
            {step === 2 && (
              <Button onClick={submitCompetitors} disabled={busy}>
                {busy
                  ? "저장 중…"
                  : competitors.some((c) => c.name.trim() && c.url.trim())
                    ? "다음"
                    : "건너뛰기"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
            {step === 3 && (
              <Button onClick={submitTone} disabled={busy}>
                {busy ? "저장 중…" : "다음"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
            {step === 4 && (
              <Button onClick={finish} disabled={busy}>
                {busy ? "저장 중…" : "완료하고 대시보드로"}
                <Check className="h-4 w-4" />
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
