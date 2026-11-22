import type { components } from "@/lib/api-types";

/**
 * 근거 진단 화면의 고정 문구.
 *
 * 원칙: 화면에 나가는 문장은 "리뷰에 무엇이 얼마나 적혀 있는지"(관찰)까지만 말한다.
 * 원인·효과는 단정하지 않고, 점주가 직접 확인할 것으로 안내한다. 건수의 단위는 '리뷰'다.
 */

export type Polarity = "pos" | "neg";
export type SufficiencyLevel = components["schemas"]["Sufficiency"]["level"];

export const POLARITY_LABEL: Record<Polarity, string> = { neg: "불만", pos: "호평" };

/** 자료 충분도 — 자료량 안내일 뿐 통계적 신뢰도가 아니다. 숫자(%)로 바꿔 보여주지 않는다. */
export const SUFFICIENCY: Record<SufficiencyLevel, { label: string; hint: string; tone: string }> = {
  low: {
    label: "판단 자료가 적음",
    hint: "리뷰가 더 쌓이기 전까지는 참고용으로만 보세요. 리뷰가 적다는 것이 평가가 낮다는 뜻은 아닙니다.",
    tone: "bg-level-warn/15 text-amber-700",
  },
  fair: {
    label: "참고할 만한 양",
    hint: "큰 흐름은 볼 수 있지만, 항목별로는 건수를 함께 확인하세요.",
    tone: "bg-muted text-muted-foreground",
  },
  good: {
    label: "자료가 충분한 편",
    hint: "이 기간의 흐름을 보기에 충분한 양입니다. 그래도 항목별 건수는 함께 확인하세요.",
    tone: "bg-delta-up/10 text-delta-up",
  },
};

export const PLATFORM_LABEL: Record<string, string> = {
  naver: "네이버",
  csv: "CSV 업로드",
  google: "구글",
};

/** 분석에서 제외할 때 고르는 이유(직접 입력도 가능). */
export const EXCLUDE_REASONS = ["중복 수집", "우리 매장과 무관한 내용"];

type AspectCopy = {
  /** 리뷰만으로는 알 수 없어 점주가 직접 확인할 것 */
  checks: string[];
  /** 실행 과제 입력을 돕는 후보 — 처방이 아니라 '검토해 볼 것' */
  ideas: string[];
};

const ISSUE_COPY: Record<string, AspectCopy> = {
  대기시간: {
    checks: [
      "피크 시간대의 실제 대기 기록(요일·시간대별)",
      "대기 중 안내 방식(예상 시간 고지, 호출 방법)과 주문 누락 여부",
    ],
    ideas: ["예상 대기시간 안내 개선", "피크 시간대 웨이팅 등록 방식 점검", "주문 누락 확인 절차 추가"],
  },
  친절: {
    checks: [
      "리뷰가 작성된 날짜·시간대의 근무 상황",
      "주문·계산·문의 중 어느 단계의 응대가 언급됐는지",
    ],
    ideas: ["응대 기본 멘트 정리해 공유", "바쁜 시간대 역할 분담 조정", "불편 접수 시 안내 절차 정하기"],
  },
  청결: {
    checks: [
      "리뷰에서 지적된 위치(테이블·바닥·화장실 등)의 점검 기록",
      "마감·오픈 청소 순서와 담당",
    ],
    ideas: ["마감 청소 체크리스트 운영", "피크 시간 사이 테이블 점검 추가", "화장실 점검 시간표 게시"],
  },
  가격: {
    checks: ["최근 가격·구성을 바꾼 시점과 리뷰 작성 시점", "가격과 함께 언급된 메뉴·양"],
    ideas: ["가격 조정 사유 안내문 게시", "세트·구성 메뉴 검토", "메뉴판에 양·구성 표기 보완"],
  },
  맛: {
    checks: ["언급된 메뉴와 그날의 조리 담당·재료 변경 여부", "같은 메뉴에 대한 다른 날짜의 리뷰"],
    ideas: ["언급된 메뉴 레시피·간 점검", "제공 전 온도 확인 절차 추가", "변경한 메뉴의 반응 따로 기록"],
  },
  분위기: {
    checks: ["리뷰가 짚은 요소(소음·좌석 간격·온도 등)를 같은 시간대에 직접 확인"],
    ideas: ["음악 볼륨·좌석 배치 조정", "혼잡 시간대 안내 문구 추가"],
  },
};

const ISSUE_FALLBACK: AspectCopy = {
  checks: ["리뷰 원문에서 언급된 대상(주차·예약·위치 안내 등)을 직접 확인"],
  ideas: ["네이버 플레이스 안내 정보 보완"],
};

const STRENGTH_COPY: AspectCopy = {
  checks: ["호평이 특정 메뉴·시간대·직원에 몰려 있는지", "같은 항목을 다르게 말한 리뷰가 있는지"],
  ideas: ["호평 받은 점을 매장 소개·사진에 반영", "같은 경험을 유지할 기준 정리해 공유"],
};

export function aspectCopy(aspect: string, polarity: Polarity): AspectCopy {
  if (polarity === "pos") return STRENGTH_COPY;
  return ISSUE_COPY[aspect] ?? ISSUE_FALLBACK;
}

// ---- 날짜 표시 (YYYY-MM-DD 문자열을 시간대 변환 없이 그대로 읽는다) ----
function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return [y, m, d];
}

/** "2026-11-13" → "11/13" */
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "날짜 없음";
  const [, m, d] = parts(iso);
  return `${m}/${d}`;
}

/** "2026-10-26", "2026-11-22" → "10/26 ~ 11/22" */
export function fmtPeriod(start: string, end: string): string {
  return `${fmtDay(start)} ~ ${fmtDay(end)}`;
}

/** YYYY-MM-DD 에 days 를 더한 날짜 문자열 */
export function addDays(iso: string, days: number): string {
  const [y, m, d] = parts(iso);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** 오늘 날짜(사용자 기기 기준) YYYY-MM-DD — 실행일 입력 기본값 */
export function todayIso(): string {
  const now = new Date();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${m}-${d}`;
}

/** 근거 진단 화면으로 가는 링크 (항목을 주면 근거 패널이 바로 열린다) */
export function insightsHref(opts: {
  aspect?: string;
  polarity?: Polarity;
  range?: string;
  asOf?: string;
}): string {
  const q = new URLSearchParams();
  if (opts.aspect) q.set("aspect", opts.aspect);
  if (opts.aspect && opts.polarity) q.set("polarity", opts.polarity);
  if (opts.range) q.set("range", opts.range);
  if (opts.asOf) q.set("as_of", opts.asOf);
  const s = q.toString();
  return s ? `/insights?${s}` : "/insights";
}
