# ARCHITECTURE — 시스템 구조와 기술 결정

> 이 문서는 `TECH_SPEC.md`(요구사항)를 실제 코드 구조로 옮기는 결정사항을 담는다.
> 스펙이 이미 확정한 것(FastAPI, Supabase, Playwright, APScheduler, 반자동 답글 등)은 재논의하지 않는다.

---

## 1. 전체 구조

```
[사용자 브라우저/PWA]
   │  Supabase Auth (카카오 로그인, JWT 발급) ──────────► [Supabase Auth]
   │  데이터 요청 (Authorization: Bearer <supabase JWT>)
   ▼
[Vercel: Next.js 프론트]  ──REST/SSE──►  [VM: FastAPI api 컨테이너]
                                              │  SQLAlchemy(asyncpg)
                                              ▼
                                         [Supabase PostgreSQL + pgvector]
                                              ▲
[VM: worker 컨테이너]──────────────────────────┘
  APScheduler + Playwright
  · 매장당 1일 2회 크롤 → 분석 파이프라인 직접 호출(같은 코드베이스)
  · crawl_jobs 테이블 폴링(수동 트리거)
  · 주간 리포트(월 07:00), 알림 다이제스트(매시)
```

- **api와 worker는 같은 파이썬 패키지(`backend/app`)를 공유**하고 엔트리포인트만 다르다
  (`app.main:app` vs `python -m app.worker`). 파이프라인 코드 중복 없음.
- api ↔ worker 간 통신은 **DB 테이블(`crawl_jobs`)이 유일한 채널**이다. HTTP/큐 없음.
  - `POST /internal/crawl:trigger` → `crawl_jobs`에 row insert → worker가 10초 주기로 폴링해 처리.
  - 스펙의 "메시지큐 금지" 원칙을 지키면서 데모용 수동 트리거를 구현하는 방법.
- 프론트는 **Supabase를 Auth 용도로만** 사용한다. 데이터 접근은 전부 FastAPI 경유.
  Supabase PostgREST 직접 호출 금지 → 모든 테이블에 RLS "deny all" 을 걸어 이중 안전장치로 삼는다
  (백엔드는 service_role 커넥션이라 RLS 영향 없음).

## 2. 저장소 레이아웃 (모노레포)

```
we-meet_AI_review/
├── CLAUDE.md
├── docs/                       # 본 문서들
├── docker-compose.yml          # 배포용: api + worker + caddy
├── docker-compose.dev.yml      # 로컬 개발용: postgres(pgvector 포함)
├── .env.example
├── backend/
│   ├── pyproject.toml          # uv 또는 pip. ruff + pytest 설정 포함
│   ├── Dockerfile              # api용 (slim)
│   ├── Dockerfile.worker       # worker용 (playwright chromium 포함)
│   ├── selectors.yaml          # 네이버 크롤링 셀렉터 (외부화)
│   ├── prompts/                # LLM 프롬프트, 파일명에 버전: classify_v1.md 등
│   ├── migrations/             # 001_init.sql, 002_....sql (Supabase CLI로 적용)
│   ├── tests/
│   └── app/
│       ├── main.py             # FastAPI 앱 생성, 라우터 등록, CORS
│       ├── config.py           # pydantic-settings (env 로딩)
│       ├── db.py               # async engine/session 팩토리
│       ├── models.py           # SQLAlchemy 2.0 모델 (schema.sql과 1:1)
│       ├── deps.py             # 인증/소유권 의존성
│       ├── schemas/            # Pydantic 요청/응답 DTO
│       ├── routers/            # stores, reviews, replies, dashboard, reports,
│       │                       #   compare, assistant, internal
│       ├── services/           # 비즈니스 로직 (라우터는 얇게)
│       ├── collectors/         # base.py, naver.py, csv_import.py  (P2: google.py)
│       ├── pipeline/           # analyze, embed, stats, reply_gen, report_gen
│       ├── llm/                # client.py (유일한 LLM 게이트웨이), schemas.py
│       ├── notify/             # kakao.py, webpush.py, dispatch.py
│       └── worker.py           # APScheduler 엔트리포인트
└── frontend/                   # Next.js 15 — docs/FRONTEND.md 참고
```

## 3. 스펙에 없던 것을 정한 결정들 (이유 포함)

| # | 결정 | 이유 |
|---|---|---|
| 1 | **DB 접근 = SQLAlchemy 2.0 async + asyncpg** (supabase-py 미사용) | 타입 있는 모델로 하위 모델(Sonnet)의 SQL 실수를 구조적으로 차단. supabase-py는 PostgREST 래퍼라 조인/집계 쿼리에 부적합. 마이그레이션의 원본은 SQL 파일이고, `models.py`는 이를 수동으로 미러링(테이블 12개 수준이라 부담 없음). Alembic autogenerate 사용 금지 — SQL 파일과 이중 원천이 되면 반드시 어긋난다 |
| 2 | **Supabase 접속은 Session Pooler(포트 5432, IPv4)** | Direct connection은 무료 티어에서 IPv6 전용이라 VM에서 안 될 수 있음. Transaction pooler(6543)는 prepared statement 문제로 asyncpg와 궁합 나쁨. api 서버 1대 + pool_size 5면 session pooler로 충분. 만약 6543을 써야 하면 `connect_args={"statement_cache_size": 0}` 필수 |
| 3 | **JWT 검증 = PyJWT + `SUPABASE_JWT_SECRET`(HS256)** | 미들웨어 아닌 FastAPI 의존성(`deps.get_current_user`)으로 구현. 프로젝트가 신형 비대칭 키(ES256)를 쓰면 JWKS URL 검증으로 교체 — `deps.py` 한 곳만 수정하면 되게 격리 |
| 4 | **LLM 모델 배정**: 분류/비서 라우터 = `claude-haiku-4-5`, 답글·리포트·비서 답변 = `claude-sonnet-5` | 분류는 대량·단순(리뷰 10~20건 배치)이라 Haiku($1/$5 per MTok)로 충분하고 비용이 사실상 0에 수렴. 생성 품질이 사용자에게 직접 보이는 답글/리포트는 Sonnet 5($3/$15, 2026-08까지 인트로 $2/$10). 모델 ID는 env(`LLM_MODEL_CLASSIFY`, `LLM_MODEL_GENERATE`)로 오버라이드 가능 — 스펙의 "프로바이더 추상화" 요구 충족 |
| 5 | **LLM JSON 강제 = Anthropic structured outputs (`client.messages.parse` + Pydantic)** | 스펙은 "JSON 스키마 강제 + 파싱 실패 시 1회 재시도"를 요구하는데, structured outputs를 쓰면 스키마 위반 자체가 사실상 사라진다. 재시도 1회는 API 오류(429/5xx) 대비로 유지 |
| 6 | **초기 백필 분류는 Message Batches API** | 매장 온보딩 시 과거 리뷰 수백 건을 한 번에 분류해야 함. Batches는 50% 할인 + 실시간성 불필요. 신규 리뷰 증분 분석은 일반 호출 |
| 7 | **스펙 DDL에 빠진 테이블 4개 추가**: `crawl_jobs`, `kakao_tokens`, `push_subscriptions`, `store_settings` | ① 수동 크롤 트리거 채널 ② 카카오 "나에게 보내기"는 사용자별 refresh token을 서버가 보관·갱신해야 발송 가능 ③ 웹푸시 구독 정보 저장 필요 ④ 톤 프로필(사장님 기존 답글 3~5개 few-shot) 저장처. 상세는 `schema.sql` |
| 8 | **HTML 스냅샷은 DB가 아닌 worker 컨테이너 볼륨**(`/data/snapshots/`, 7일 로테이션) | Supabase 무료 500MB를 원본 HTML로 낭비하지 않기 위함 |
| 9 | **SSE는 EventSource가 아닌 fetch 스트림으로 소비** | EventSource는 Authorization 헤더를 못 붙임. 프론트에서 fetch + ReadableStream 파서 사용 (FRONTEND.md) |
| 10 | **프론트 타입은 FastAPI OpenAPI에서 자동 생성** (`openapi-typescript`) | 3인 팀에서 API 계약 어긋남이 가장 흔한 사고. 백엔드 스키마 변경 → `npm run gen:api` 한 줄로 프론트 타입 동기화 |

## 4. 데이터 흐름 요약

### 수집→분석 (P0 핵심 루프, worker 프로세스)
```
APScheduler(09:00/21:00 ± 지터) 또는 crawl_jobs 폴링
 → collectors/naver.py (Playwright, selectors.yaml, 증분수집·중복키)
 → reviews INSERT (on conflict do nothing)
 → pipeline/analyze.py: 신규 리뷰 10~20건 배치 → llm/client.py (Haiku, ReviewAnalysis 스키마)
 → review_analysis INSERT + pipeline/stats.py 로 weekly_aspect_stats UPSERT
 → urgent=true 또는 rating<=2 → notify/dispatch.py 즉시 발송, 나머지 부정 → 1시간 다이제스트
 → pipeline/embed.py: BGE-M3 임베딩 → review_embeddings INSERT
```

### AI 비서 (P1, api 프로세스, SSE)
```
POST /stores/{id}/assistant/messages
 → llm/client.py 라우터 호출 (Haiku, RouterDecision 스키마: intent + 파라미터)
 → intent별로 services/assistant_queries.py 의 템플릿 쿼리 실행
    (stats → weekly_aspect_stats, evidence → pgvector 유사도 + 메타필터, both → 둘 다)
 → 조회 결과를 컨텍스트로 최종 답변 스트리밍 (Sonnet) → SSE로 중계, 완료 후 chat_messages 저장
 → 조회 결과가 비면 LLM 호출 없이 "데이터 부족" 정형 응답
```

### 주간 리포트 (P1, worker, 월 07:00)
```
weekly_aspect_stats 4주치 + 급증 키워드 + 경쟁매장 통계 → 프롬프트 조립
 → Sonnet (WeeklyReport 스키마) → 서버측 수치 검증(프롬프트에 없는 숫자 등장 시 1회 재생성)
 → reports INSERT → 알림 발송
```

## 5. 배포·운영

- VM 1대 (Lightsail 2GB) + `docker-compose.yml`: `api`(uvicorn), `worker`, `caddy`(HTTPS 자동).
- 프론트는 Vercel. `NEXT_PUBLIC_API_URL`로 백엔드 도메인 지정.
- 로그: 파이썬 `logging` + JSON 포매터 → stdout → `docker logs`. 크롤 세션마다
  `{store_id, collected, duration_ms, status}` 1줄 기록 (발표용 성공률 수치의 원천).
- 백업: Supabase 자동(7일) + worker에 주 1회 `pg_dump` cron job 추가.
- CI: GitHub Actions — `ruff check` + `pytest` + 프론트 `tsc --noEmit`/`next build`. 자동 배포는 선택.

## 6. 데모 이중화 (설계 원칙 3)

- `backend/scripts/seed_demo.py`: 가상 매장 2곳 + 경쟁매장 + 리뷰 300건 + 분석결과 + 4주치
  통계 + 리포트 1건을 통째로 넣는 시드 스크립트. **모든 화면은 이 시드만으로 완전 동작해야 한다.**
- 라이브 크롤은 `POST /internal/crawl:trigger`(관리자 키 인증)로 데모 중 1회 시연.
