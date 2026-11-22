# FRONTEND — Next.js PWA 구현 지침

> 대상: `frontend/`. 프론트는 본 백엔드 REST API의 소비자다. **데이터는 전부 FastAPI 경유** —
> Supabase 클라이언트는 로그인/세션 용도로만 사용한다 (DB 직접 쿼리 금지, RLS로 막혀 있음).

## 1. 스택 확정

| 영역 | 선택 | 이유 |
|---|---|---|
| 프레임워크 | **Next.js 15 (App Router) + TypeScript** | Vercel 배포, 스펙 확정 사항 |
| 스타일 | **Tailwind CSS + shadcn/ui** | 3인 팀에서 디자인 시스템 직접 구축 금지. 컴포넌트는 shadcn 복사-수정 |
| 서버 상태 | **TanStack Query v5** | 캐싱/리페치/무한스크롤(리뷰 인박스) 내장. Redux/Zustand 등 전역 상태 라이브러리 도입 금지 — 서버 상태는 Query, 나머지는 useState/URL |
| 인증 | **@supabase/ssr** (카카오 소셜 로그인) | 세션은 쿠키, `middleware.ts`로 보호 라우트 처리 |
| API 타입 | **openapi-typescript** | `npm run gen:api` → FastAPI `/openapi.json`에서 `src/lib/api-types.d.ts` 생성. 손으로 API 타입 정의 금지 |
| 차트 | **Recharts** | 대시보드 추이/aspect 바 차트 |
| PWA | **Serwist** (next-pwa 후속) | 오프라인은 불필요, 설치 가능(manifest) + 웹푸시 수신이 목적 |
| 폼 | react-hook-form + zod | CSV 업로드, 온보딩 폼 |

## 2. 디렉토리 구조

```
frontend/
├── public/manifest.json, icons/
├── src/
│   ├── middleware.ts               # 미로그인 → /login 리다이렉트
│   ├── app/
│   │   ├── (auth)/login/page.tsx           # 카카오 로그인 버튼만
│   │   ├── (app)/layout.tsx                # 사이드바/하단탭 + StoreProvider
│   │   ├── (app)/onboarding/page.tsx       # 매장등록→네이버URL→경쟁매장→톤프로필→알림동의
│   │   ├── (app)/dashboard/page.tsx
│   │   ├── (app)/inbox/page.tsx            # 리뷰 인박스 (핵심 화면)
│   │   ├── (app)/reports/page.tsx
│   │   ├── (app)/compare/page.tsx
│   │   ├── (app)/assistant/page.tsx        # 채팅 UI (SSE)
│   │   └── (app)/settings/page.tsx
│   ├── components/                 # shadcn ui/ + 도메인 컴포넌트
│   │   ├── review/ReviewCard.tsx, ReplyDrawer.tsx, SeverityBadge.tsx
│   │   ├── dashboard/ScoreCard.tsx, TrendChart.tsx, AspectBars.tsx
│   │   └── assistant/ChatMessages.tsx, ChatInput.tsx
│   ├── lib/
│   │   ├── supabase/client.ts, server.ts   # @supabase/ssr 표준 패턴
│   │   ├── api.ts                          # ★ fetch 래퍼 (아래 §3)
│   │   ├── api-types.d.ts                  # 자동 생성 — 수동 편집 금지
│   │   ├── sse.ts                          # fetch 기반 SSE 파서 (아래 §5)
│   │   └── push.ts                         # 웹푸시 구독 등록
│   └── hooks/                      # useReviews, useDashboard, useAssistant ...
└── next.config.ts                  # Serwist 래핑
```

## 3. API 클라이언트 (`lib/api.ts`) — 모든 백엔드 호출의 단일 통로

```ts
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const supabase = createClient();                       // browser client
  const { data: { session } } = await supabase.auth.getSession();
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session?.access_token}`,
      ...init?.headers,
    },
  });
  if (res.status === 401) { /* supabase.auth.refreshSession() 1회 후 재시도, 실패 시 /login */ }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}
```

- 컴포넌트에서 `fetch` 직접 호출 금지. 반드시 `api()` 또는 이를 감싼 훅 사용.
- 데이터 훅 패턴: `useQuery({ queryKey: ["reviews", storeId, filters], queryFn: ... })`.
  인박스는 `useInfiniteQuery` + 커서(`?cursor=&limit=20`).

## 4. 화면별 요구사항

### 인박스 (`/inbox`) — 가장 중요한 화면
- 필터 칩: 전체 / 부정 / 긴급 / 미답변 (URL searchParams와 동기화).
- `ReviewCard`: 마스킹 작성자, 별점, 본문, `SeverityBadge`(urgent는 빨강), aspect 태그.
- 카드 클릭 → `ReplyDrawer`(bottom sheet):
  1. 톤 선택(정중/친근/사과) → `POST /reviews/{id}/reply:generate` → 초안 표시(로딩 스켈레톤)
  2. 초안 인라인 수정 가능
  3. **[승인하고 답글 달러가기]** 버튼 = ① `POST /replies/{id}:approve` ② `navigator.clipboard.writeText(draft)`
     ③ `window.open(스마트플레이스 답글 URL)` ④ "복사됨 — 붙여넣기만 하세요" 토스트.
     서버는 네이버에 아무것도 게시하지 않는다(반자동 확정 사항).

### 대시보드 (`/dashboard`)
- 종합 평판 점수(큰 숫자 + 전주 대비 증감), 주별 추이 라인차트, aspect별 긍/부정 바차트,
  급증 키워드 칩. 데이터는 `GET /dashboard?range=4w` 한 번으로 받는다(프론트 집계 금지).
- (T-F8) 점수 카드 아래 자료 충분도(`sufficiency` + 기간 + 분석 리뷰 수)와 "반복 문제 후보" 카드가 추가됐다.
  후자만 `GET /insights`를 따로 호출한다(근거 진단 화면과 같은 쿼리 캐시를 공유) — 집계는 여전히 서버가 한다.

### 리포트 (`/reports`)
- diagnosis를 level별 색상 카드(crit=빨강/warn=노랑/strength=초록/opportunity=파랑)로,
  각 카드에 evidence 수치 강조. prescriptions는 체크리스트 형태.

### 근거 진단 (`/insights`) — T-F8, 스펙 외 추가
- 화면 상태는 전부 URL: `?range=4w&aspect=대기시간&polarity=neg&as_of=YYYY-MM-DD`.
  `aspect`가 있으면 근거 패널이 열린다 — 대시보드·리포트에서 이 URL로 바로 들어온다(`lib/insight-copy.insightsHref`).
- 구성(위→아래): 분석 범위 카드(`CoverageCard` — 기간·분모·빠진 리뷰 건수·자료 충분도) →
  반복 문제 후보 / 호평 항목(`InsightCard` — "N건 중 M건", 반복 주 수, 직전 기간, 근거 문장 미리보기) →
  실행 과제(`ActionList` — 실행 전/후 건수) → 확인이 필요한 리뷰 + 분석 제외 내역(`ReviewChecks`).
- 근거 패널(`EvidenceDrawer`): 요약 문장 → 사실 표(분석 범위·관련 리뷰·주별 언급·함께 나온 말·다른 경험·
  자료 한계·직접 확인할 것) → 실행 과제 기록 폼 → 근거 리뷰 원문(근거 문장 강조 `HighlightedBody`) →
  다르게 말한 리뷰.
- 문구 원칙(`lib/insight-copy.ts`에 모음): 관찰까지만 말하고 원인·효과를 단정하지 않는다. 단위는 "리뷰 N건".
  자료 충분도는 등급 이름 + 실제 건수 + 기준값으로만 표시하고 % 로 바꾸지 않는다.
  검토 신호는 "가짜" 같은 판정 표현을 쓰지 않는다. 건수·비율은 서버가 계산한 값만 쓴다(프론트 집계 금지).
- 다른 화면 연결: 대시보드 `ScoreCard` 하단에 자료 충분도, `IssueTeaser`(반복 문제 후보 상위 3개),
  리포트 `DiagnosisCard`의 "근거 리뷰 보기"(리포트와 같은 4주 = `as_of`), 인박스 `ReviewCard`의
  근거 문장 강조와 "분석 제외" 뱃지.

### 비교 (`/compare`)
- aspect별 우리 vs 경쟁 수평 바 비교 + 한 줄 인사이트.

### AI 비서 (`/assistant`)
- 채팅 UI. 전송 → SSE 스트리밍 토큰을 실시간 append. 근거 리뷰는 답변 하단에 인용 카드로.
- 히스토리는 `GET /assistant/messages`로 초기 로딩.

### 온보딩 (`/onboarding`) — 스텝 위저드
1. 매장 정보 → `POST /stores`
2. 네이버 플레이스 URL → `POST /stores/{id}/channels` (첫 수집 자동 트리거됨)
3. 경쟁매장 URL 2~3개 (선택, is_competitor=true)
4. 톤 프로필: 기존 답글 3~5개 붙여넣기 → `PUT /stores/{id}/settings`
5. 알림: 카카오 talk_message 동의(카카오 로그인 재동의 플로우) + 웹푸시 권한 요청(`lib/push.ts`)
   - iOS는 PWA 설치 후에만 푸시 가능 → 설치 안내 배너 표시.

## 5. SSE 소비 (`lib/sse.ts`)

EventSource는 Authorization 헤더를 못 붙이므로 **fetch 스트림**으로 파싱한다:

```ts
export async function* sseStream(path: string, body: unknown): AsyncGenerator<string> {
  const res = await fetch(url, { method: "POST", headers: authHeaders(), body: JSON.stringify(body) });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // "\n\n" 단위로 이벤트 분리, "data: " 접두어 제거 후 yield. "[DONE]"이면 종료
  }
}
```

## 6. PWA·웹푸시

- `manifest.json`: standalone, 512 아이콘, theme_color. Serwist 기본 런타임 캐시만(오프라인 페이지 불필요).
- `lib/push.ts`: `Notification.requestPermission()` → `registration.pushManager.subscribe({userVisibleOnly:true, applicationServerKey: VAPID_PUBLIC})` → `POST /push/subscribe`.
- 서비스워커 `push` 이벤트: `{title, body, url}` 페이로드 → `showNotification`, 클릭 시 url 열기.

## 7. 데모 모드

- 시드 데이터(백엔드 seed_demo.py)만으로 전 화면이 완전 동작해야 한다. 프론트에 데모 분기 코드를 넣지 말 것 — 데모냐 아니냐는 DB 내용 차이일 뿐이다.
