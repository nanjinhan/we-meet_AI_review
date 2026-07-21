# TASKS — 작업 단위 목록

> 사용법: 하위 모델(Opus/Sonnet)에게 **"docs/TASKS.md의 T-XX를 수행해"** 라고 지시한다.
> 각 태스크는 한 세션에 끝나는 크기다. 선행 태스크(Deps)가 완료되지 않았으면 시작하지 말 것.
> 모든 태스크 공통 완료 조건: `ruff check` 통과, 관련 테스트 통과, CLAUDE.md 규칙 위반 없음.

## Phase 0 — 뼈대 (1주차)

### T-01. 저장소 스캐폴딩
- 내용: ARCHITECTURE.md §2의 디렉토리 구조 생성. `backend/pyproject.toml`(BACKEND.md §0 의존성),
  `docker-compose.dev.yml`(pgvector/pgvector:pg15 이미지), `.env.example`(config.py의 전 항목),
  빈 FastAPI 앱(`GET /healthz` → `{"ok": true}`), `frontend/`는 create-next-app(TS, Tailwind, App Router).
- 완료 조건: `uvicorn app.main:app` 기동, `docker compose -f docker-compose.dev.yml up` 후 psql 접속 가능, `npm run dev` 기동.

### T-02. DB 마이그레이션 + 모델
- Deps: T-01
- 내용: `docs/schema.sql` → `backend/migrations/001_init.sql`(+ dev 전용 `000_dev_auth_stub.sql`),
  `app/models.py`에 SQLAlchemy 모델 전체, `app/db.py`.
- 완료 조건: 로컬 postgres에 마이그레이션 적용 후 모든 모델로 insert/select 왕복하는 pytest 통과.

### T-03. 인증 의존성
- Deps: T-02
- 내용: BACKEND.md §3의 `deps.py` 전체 + 401/404 케이스 테스트(가짜 JWT를 secret으로 서명해 검증).
- 완료 조건: 잘못된 서명/만료/타 사용자 store 접근이 각각 401/401/404.

## Phase 1 — 수집 (2~3주차)

### T-04. collectors 기반 + CSV 임포트
- Deps: T-02
- 내용: `collectors/base.py`(RawReview, dedup_key, mask_author), `collectors/csv_import.py`,
  라우터 `POST /stores/{id}/reviews:import`, stores/channels CRUD 라우터(BACKEND.md §9 stores.py).
- 완료 조건: 샘플 CSV 50행 업로드 → reviews 50행, 중복 재업로드 시 0행 추가.

### T-05. 네이버 크롤러
- Deps: T-04
- 내용: `collectors/naver.py`(BACKEND.md §5), `selectors.yaml`, HTML 스냅샷 저장/로테이션.
  실제 셀렉터 값은 모바일 플레이스 페이지를 열어 채운다(사람 확인 필요 — 셀렉터 값만 비워두고 구조 완성해도 됨).
- 완료 조건: 저장된 HTML 픽스처에서 파싱 테스트 통과. 증분 중단 로직 단위 테스트.

### T-06. 워커 + 스케줄 + crawl_jobs
- Deps: T-05
- 내용: `app/worker.py`(BACKEND.md §8의 잡 5종), `POST /internal/crawl:trigger`,
  0건 2연속 자가진단 기록(알림 발송은 T-10에서 연결).
- 완료 조건: crawl_jobs에 pending insert → 워커가 집어 done 처리하는 통합 테스트(수집기는 mock).

## Phase 2 — AI 파이프라인 (3~5주차)

### T-07. LLM 게이트웨이
- Deps: T-01
- 내용: `llm/schemas.py`, `llm/client.py`(BACKEND.md §4), `prompts/classify_v1.md`, `prompts/reply_v1.md`.
  프롬프트는 한국어, 분류 기준·가드레일 명시.
- 완료 조건: generate()를 mock한 단위 테스트 + (수동) 실제 리뷰 5건 분류 스모크 스크립트 `scripts/smoke_llm.py`.

### T-08. 분석 파이프라인 + 주간 집계
- Deps: T-06, T-07
- 내용: `pipeline/analyze.py`, `pipeline/stats.py`, `pipeline/embed.py`(BGE-M3 lazy 로딩).
  수집 완료 후 자동 호출 연결. 실패 배치 `model_ver='failed'` 처리.
- 완료 조건: 리뷰 30건 → 분석 30행 + weekly_aspect_stats 정확성 테스트(수기 계산과 대조), LLM mock.

### T-09. 답글 생성 + 승인 플로우
- Deps: T-07
- 내용: `pipeline/reply_gen.py`, replies 라우터 2종, store_settings(톤 프로필) CRUD.
- 완료 조건: generate→수정→approve 왕복 API 테스트. 가드레일 문구가 프롬프트 파일에 존재.

## Phase 3 — 알림 (5~6주차)

### T-10. 카카오 + 웹푸시 + 디스패처
- Deps: T-08
- 내용: `notify/` 3파일, `auth.py` 라우터(카카오 콜백, push/subscribe), 다이제스트 워커 잡 연결,
  urgent 즉시 발송 연결, alerts 로깅.
- 완료 조건: httpx/pywebpush mock 테스트. 토큰 refresh 로직 테스트(만료 토큰 → 갱신 → 재발송).

## Phase 4 — 대시보드·리포트·비교 (6~8주차)

### T-11. 대시보드 API + 점수 산식
- Deps: T-08
- 내용: `services/score.py`, `GET /dashboard?range=4w`, 리뷰 인박스 `GET /reviews`(커서 페이지네이션·필터).
- 완료 조건: 점수 산식 단위 테스트, 커서 경계(마지막 페이지) 테스트.

### T-12. 주간 리포트 생성기
- Deps: T-08, T-10
- 내용: `pipeline/report_gen.py`, `prompts/report_v1.md`, 수치 검증 로직, reports 라우터, 워커 잡 연결.
- 완료 조건: "프롬프트에 없는 숫자" 케이스에서 재생성 분기 타는 테스트(LLM mock 2회 응답).

### T-13. 경쟁매장 비교
- Deps: T-11
- 내용: 경쟁 채널 수집·분석 경로 검증(답글·알림 미생성 확인), `GET /compare`.
- 완료 조건: 경쟁 채널 리뷰에 replies/alerts가 생기지 않는 테스트.

## Phase 5 — AI 비서 (9~10주차)

### T-14. 비서 하이브리드 백엔드
- Deps: T-08
- 내용: `prompts/assistant_router_v1.md`·`assistant_answer_v1.md`, `services/assistant_queries.py`
  (BACKEND.md §10 함수 4종), assistant 라우터(SSE), chat_messages 저장, 데이터 부족 정형 응답.
- 완료 조건: intent 3종(stats/evidence/both) 각각 mock LLM으로 E2E 테스트. 데이터 0건 시 LLM 미호출 검증.

## Phase F — 프론트 (3주차부터 백엔드와 병렬, FRONTEND.md 준수)

### T-F1. 프론트 기반: 인증 + API 클라이언트
- Deps: T-03
- 내용: @supabase/ssr 셋업, 카카오 로그인, middleware, `lib/api.ts`, openapi-typescript 파이프라인, (app) 레이아웃.
- 완료 조건: 로그인→보호 페이지 진입→로그아웃. `npm run gen:api` 동작.

### T-F2. 온보딩 위저드
- Deps: T-F1, T-04 — 5단계 스텝 (FRONTEND.md §4)

### T-F3. 리뷰 인박스 + 답글 드로어
- Deps: T-F1, T-09 — 무한스크롤, 필터, 승인→클립보드→딥링크 플로우

### T-F4. 대시보드 화면
- Deps: T-F1, T-11 — Recharts 차트 3종 + 점수 카드

### T-F5. 리포트·비교 화면
- Deps: T-F1, T-12, T-13

### T-F6. PWA + 웹푸시
- Deps: T-F1, T-10 — Serwist, manifest, push 구독, iOS 설치 배너

### T-F7. 비서 채팅 화면
- Deps: T-F1, T-14 — `lib/sse.ts` + 채팅 UI

## Phase 6 — 마감 (11~12주차)

### T-15. 데모 시드 + 운영 마감
- Deps: 전체
- 내용: `scripts/seed_demo.py`(매장 2+경쟁 2, 리뷰 300, 분석·통계·리포트 포함),
  배포 compose + Caddyfile, GitHub Actions CI, pg_dump 잡, 로그 점검.
- 완료 조건: 빈 DB → 시드 → 전 화면 데이터 표시. VM에서 compose up으로 전체 기동.
