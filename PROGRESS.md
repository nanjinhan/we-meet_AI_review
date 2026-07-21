# PROGRESS — 진행 상황 인수인계

> 이 파일은 "어디까지 했고, 어디부터 이어서 하면 되는지"를 기록하는 인수인계 문서다.
> **누가(나 / 다른 사람 / Claude Code) 이어받아도 이 파일만 보면 다음 작업을 시작할 수 있어야 한다.**
> GitHub에 올릴 때마다 이 파일을 최신 상태로 갱신한다.
>
> 최종 갱신: **2026-07-21** · 진행: **T-11까지 완료 (백엔드 Phase 0~4 일부), 다음은 T-12**

---

## 1. 프로젝트 한 줄 요약

네이버 플레이스 리뷰를 수집·분석해 소상공인에게 **알림 / AI답글 / 리포트 / 비교 / AI비서**를 제공하는 B2B SaaS (3인 학생팀, 12주 MVP).
요구사항 원천은 `docs/TECH_SPEC.md`. 작업 단위는 `docs/TASKS.md`(T-01~T-15, T-F1~T-F7).

## 2. 스택 (실제 구현 기준)

- 백엔드: Python **3.12 목표**(현재 개발 venv는 3.14), FastAPI, SQLAlchemy 2.0 async + asyncpg, APScheduler(워커), Playwright(크롤러)
- DB: PostgreSQL 15 + pgvector (로컬은 docker), 마이그레이션은 `backend/migrations/*.sql`
- **LLM: Google Gemini 무료 티어** (원 스펙은 Anthropic이나 유료 회피 위해 교체 — `backend/app/llm/client.py` 한 파일만 프로바이더 의존)
- 프론트: Next.js 15 App Router + TS + Tailwind (`frontend/`, 아직 스캐폴딩만)

## 3. 진행 현황 (체크리스트)

### 백엔드
- [x] **T-01** 저장소 스캐폴딩 (FastAPI `/healthz`, docker DB, Next.js)
- [x] **T-02** DB 마이그레이션 + SQLAlchemy 모델 14종
- [x] **T-03** 인증 의존성 (JWT 검증, 소유권 검사, 401/404)
- [x] **T-04** collectors 기반 + CSV 임포트 + stores/channels CRUD
- [x] **T-05** 네이버 크롤러 (`naver.py`, `selectors.yaml` — 실제 셀렉터값은 미기입)
- [x] **T-06** 워커 + 스케줄 + crawl_jobs 폴링 + 자가진단
- [x] **T-07** LLM 게이트웨이 (Gemini, structured outputs, 프롬프트 파일)
- [x] **T-08** 분석 파이프라인 + 주간 집계 (analyze/stats/embed)
- [x] **T-09** 답글 생성 + 승인 플로우 (반자동)
- [x] **T-10** 카카오 + 웹푸시 + 디스패처 + 다이제스트
- [x] **T-11** 대시보드 API + 점수 산식 + 리뷰 인박스(커서 페이지네이션)  ← **여기까지 완료**
- [ ] **T-12** 주간 리포트 생성기  ← **다음 할 것**
- [ ] **T-13** 경쟁매장 비교
- [ ] **T-14** AI 비서 하이브리드 백엔드
- [ ] **T-15** 데모 시드 + 운영 마감(배포 compose, CI 등)

### 프론트 (아직 스캐폴딩만, T-F1부터 미착수)
- [ ] T-F1 인증+API클라이언트 / T-F2 온보딩 / T-F3 인박스+답글 / T-F4 대시보드 / T-F5 리포트·비교 / T-F6 PWA+웹푸시 / T-F7 비서채팅

## 4. 다음 작업 (T-12) — 시작점

`docs/TASKS.md`의 **T-12** 참고. 요약:
- `backend/app/pipeline/report_gen.py`: `generate_weekly_report(db, store_id, week_start)` — 4주치 통계 + 급증 키워드 + 경쟁 통계를 프롬프트에 넣어 `generate("report_v1", ..., WeeklyReportOut)`.
- `backend/prompts/report_v1.md`: 진단(위험/주의/강점/기회, **근거 수치 필수**) + 처방. 가드레일: 집계값만 인용.
- **수치 검증(핵심)**: `diagnosis.evidence` 안의 숫자가 프롬프트에 넣은 집계값 집합에 없으면 **1회 재생성**, 재실패 시 해당 항목 제거 → `reports` insert.
- reports 라우터: `GET /stores/{id}/reports/latest`, `GET /stores/{id}/reports/{report_id}`.
- 워커 잡 연결: 월 07:00 `generate_weekly_reports`(worker.py 스텁 존재) → report_gen 실제 호출 + `dispatch.send_report_ready`.
- 완료 조건: "프롬프트에 없는 숫자" 케이스에서 재생성 분기 타는 테스트(LLM mock 2회 응답).
- 참고: `WeeklyReportOut`/`Diagnosis`/`Prescription` 스키마는 `llm/schemas.py`에 이미 있음. LLM 호출은 `generate()`(mock) 사용.

## 5. 지금까지의 주요 결정/이탈 (이어받는 사람 필독)

1. **LLM = Gemini 무료 티어** (원 스펙 Anthropic 아님). `config.py`의 `gemini_api_key`, 모델 `gemini-2.0-flash`(분류)/`gemini-2.5-flash`(생성). 교체는 `llm/client.py`만.
2. **파싱용 beautifulsoup4 추가** (T-05): §11 "브라우저 없이 HTML 픽스처 파싱 테스트" 요구 충족용. 크롤 엔진은 여전히 Playwright(lazy import).
3. **임베딩(BGE-M3)은 best-effort** (T-08): `FlagEmbedding`+torch가 Python 3.14 휠 문제로 미설치. 미설치여도 파이프라인 정상(임베딩만 skip). AI비서 근거검색(T-14)에서만 쓰임 → 그때 3.12 venv 설치 or Gemini 임베딩으로 교체.
4. **알림은 코드+mock 완성, 실발송 키는 나중** (T-10): 카카오/웹푸시 실제 키 없이도 완료(테스트는 httpx/pywebpush mock). 발표 직전 카카오 앱 발급 → `.env`에 키만 넣으면 실발송.
5. **경쟁매장은 자체 `stores` 행 필요**: `weekly_aspect_stats` PK가 (store_id,week,aspect)라 통계 분리하려면 경쟁매장도 stores 행을 가져야 함. T-13에서 강제/검증 예정.
6. **크롤러 미해결(사람 필요)**: `selectors.yaml`의 실제 네이버 CSS 셀렉터값 미기입(구조만), 방문일 연도 파싱·`wait_for_selector` 보강은 셀렉터 확정 후.
7. **마이그레이션 3개**: 001(init) / 002(crawl_jobs.collected) / 003(review_analysis.alerted_at).
8. **점수 산식 상수**: `services/score.py`에 가중치(0.5/0.3/0.2) 분리. 대시보드는 `services/dashboard.py`가 weekly_aspect_stats + 답변율/키워드로 조립(`today` 주입 가능).

## 6. 로컬 실행 방법

```bash
# 1) DB (마이그레이션 자동 적용은 빈 볼륨 최초 1회. 이후엔 아래 6-2 참고)
docker compose -f docker-compose.dev.yml up -d

# 2) 백엔드
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -e ".[dev]"        # + google-genai, beautifulsoup4, httpx 등
cp ../.env.example .env        # ★ 각자 GEMINI_API_KEY 발급해 넣기 (aistudio.google.com/apikey)
uvicorn app.main:app --reload  # http://localhost:8000/healthz  (8000 충돌 시 --port 8010)
pytest                         # 전체 테스트

# 3) 워커(선택)
python -m app.worker

# 4) 프론트
cd ../frontend && npm install && npm run dev
```

**마이그레이션을 새로 적용하려면**(이미 볼륨 있는 경우): `docker compose -f docker-compose.dev.yml down -v` 후 재기동,
또는 개별 적용 `docker exec -i <db컨테이너> psql -U app -d reviewdb < backend/migrations/00X_*.sql`.

## 7. 테스트/품질 현황

- **pytest 70개 전부 통과**, `ruff check` 통과 (모든 태스크 공통 완료조건).
- DB 테스트는 로컬 docker postgres 사용(트랜잭션 롤백 격리). LLM/외부발송은 mock.

## 8. ⚠️ 보안

- `.env`(특히 `GEMINI_API_KEY`)는 **절대 커밋 금지** — `.gitignore`에 `backend/.env` 포함됨.
- 각자 자기 Gemini 키를 발급해 로컬 `.env`에만 넣는다. 저장소엔 `.env.example`만 있다.

## 9. 참고 문서

- `CLAUDE.md` — 프로젝트 규약(10대 규칙)
- `docs/TECH_SPEC.md` — 요구사항 원천 / `docs/TASKS.md` — 작업 단위 / `docs/ARCHITECTURE.md` / `docs/BACKEND.md` / `docs/FRONTEND.md` / `docs/schema.sql`
