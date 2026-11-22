# 리뷰 진단 AI SaaS (we-meet)

네이버 플레이스 리뷰를 자동 수집·분석해 소상공인에게 **① 부정리뷰 즉시 알림 ② AI 답글 초안 ③ 진단·처방 리포트 ④ 경쟁매장 비교 ⑤ 자연어 AI 비서 ⑥ 근거 진단**을 제공하는 B2B SaaS.

> 3인 학생팀 · 12주 MVP · 요구사항 원천은 [`docs/TECH_SPEC.md`](docs/TECH_SPEC.md)

**진행 상황: 백엔드 T-01~T-16 + 프론트 T-F1~T-F8 전부 완료 · pytest 105개 통과** — 스펙의 MVP(T-15 / T-F7까지)에 근거 진단(T-16 / T-F8)을 더했다. 남은 건 실제 배포·키 발급·인터뷰(코딩 아님). 상세는 👉 [`이어서진행.md`](이어서진행.md)

### 근거 진단 — 분석 결과를 그대로 믿으라고 하지 않는다

"서비스가 좋지 않다" 같은 요약만으로는 점주가 무엇을 고칠지 판단하기 어렵다. 그래서 분석 결과마다 **어떤 리뷰를 근거로 했는지, 몇 건 중 몇 건인지, 자료가 충분한지**를 함께 보여준다.

- **근거 연결** — "분석 리뷰 31건 중 6건에서 대기시간 불만" → 그 6건의 원문과, AI가 그렇게 판단한 문장(원문 대조를 통과한 것만 표시), 같은 항목을 다르게 말한 리뷰.
- **분석 범위와 자료 충분도** — 기간, 분모가 된 리뷰 수, 빠진 리뷰(분석 전·실패·제외·작성일 없음)를 숨기지 않는다. 자료가 적으면 "판단 자료가 적음"이라고만 표시하고, 근거 없는 신뢰도 % 는 만들지 않는다.
- **검토 신호** — 같은 리뷰가 두 경로로 들어온 중복 기록, 여러 리뷰에 반복된 같은 문장을 찾아 보여준다. 가짜로 판정하거나 자동으로 빼지 않는다 — 제외는 점주가 이유와 함께 하고, 언제든 되돌린다.
- **실행 과제** — 근거를 본 뒤 "이번 주에 실행할 행동 하나"와 실행일을 기록하면, 그 전후로 같은 항목이 리뷰에 나타난 건수를 나란히 보여준다(효과 판정은 하지 않는다).

---

## 스택

| 영역 | 사용 |
|---|---|
| 백엔드 | Python 3.12(목표) · FastAPI · SQLAlchemy 2.0 async + asyncpg · APScheduler · Playwright |
| DB | PostgreSQL 15 + pgvector (로컬은 docker) |
| LLM | **Google Gemini 무료 티어** (프로바이더 추상화 — `backend/app/llm/client.py` 한 파일만 의존) |
| 프론트 | Next.js 15 + TypeScript + Tailwind + shadcn 스타일 UI + Serwist(PWA) — 전 화면 구현 완료 |

## 빠른 시작 (로컬 개발)

```bash
# 1) DB
docker compose -f docker-compose.dev.yml up -d

# 2) 백엔드
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash. 반드시 Python 3.12(결정 18)
pip install -e ".[dev]"
cp ../.env.example .env        # ★ 각자 GEMINI_API_KEY 발급해 넣기 → https://aistudio.google.com/apikey
uvicorn app.main:app --reload --port 8010  # http://localhost:8010/healthz
pytest                         # 전체 테스트 (105개)
python -m scripts.seed_demo    # 데모 시드 (매장2+경쟁2+리뷰 350여 건+집계+리포트+근거 진단 사례)

# 3) 프론트
cd ../frontend && npm install
cp .env.local.example .env.local   # ★ API 주소(포트) + NEXT_PUBLIC_DEV_TOKEN 채우기 — 파일 안 주석 참고
npm run dev                        # http://localhost:3000 (근거 진단은 /insights)
```

> 이미 만들어 둔 로컬 DB가 있다면 새 마이그레이션(`backend/migrations/004_evidence_and_actions.sql`)을 한 번 적용해야 한다 — [`이어서진행.md`](이어서진행.md) §6.

> 🔒 `.env`(특히 `GEMINI_API_KEY`)는 **커밋 금지**. 저장소엔 `.env.example`만 있고, 각자 자기 키를 로컬 `.env`에 넣는다.

VM에 실제 배포하려면(Supabase·도메인 준비 후) 레포 루트의 `docker-compose.yml`(api+worker+caddy) —
상세는 [`이어서진행.md`](이어서진행.md) §6-1.

## 저장소 구조

```
backend/
  app/
    main.py config.py db.py deps.py models.py   # 앱 기반 + 인증 + 모델
    collectors/   # 수집기 (base / csv_import / naver)
    pipeline/     # 분석 (analyze / stats / embed / reply_gen)
    llm/          # LLM 게이트웨이 (client / schemas) — 유일한 벤더 의존점
    notify/       # 알림 (kakao / webpush / dispatch)
    routers/      # API 엔드포인트 (… / insights / actions)
    services/     # 집계·조회 로직 (dashboard / compare / insights / actions / sufficiency / review_text …)
    worker.py     # APScheduler 워커 (크롤·분석·다이제스트·DB백업, 6개 스케줄 잡)
  migrations/     # 000(로컬전용 auth스텁)~004 (SQL)
  Dockerfile / Dockerfile.worker   # 배포용 이미지 (api / worker)
  prompts/        # LLM 프롬프트 (버전 관리)
  tests/          # pytest (docker postgres 대상, 외부 호출은 mock)
frontend/         # Next.js 15 PWA — 전 화면(대시보드/인박스/근거 진단/리포트/비교/비서/온보딩) + PWA·웹푸시
docker-compose.yml       # 배포용: api + worker + caddy (DB는 Supabase 원격)
docker-compose.dev.yml   # 로컬 개발용: postgres(pgvector 포함)
Caddyfile                # 배포용 리버스 프록시 (HTTPS 자동, SSE 스트리밍 설정)
.github/workflows/ci.yml # ruff+pytest(백엔드) · tsc+build(프론트)
docs/             # TECH_SPEC / ARCHITECTURE / BACKEND / FRONTEND / TASKS / schema.sql
이어서진행.md      # 진행 인수인계 문서 (여기부터 이어서 — 새 세션은 이거부터 읽기)
CLAUDE.md         # 프로젝트 규약 (10대 규칙)
```

## 작업 방식

- 작업 단위는 [`docs/TASKS.md`](docs/TASKS.md)의 T-01~T-16 / T-F1~T-F8 — **전부 완료됨**.
- 모든 태스크 공통 완료 조건: `ruff check` 통과 · 관련 pytest 통과 · `CLAUDE.md` 규칙 준수.
- 이어서 작업하려면 [`이어서진행.md`](이어서진행.md)의 "새 세션에서 바로 시작하는 법" 절부터 — 남은 건 코딩이 아니라 실제 배포/키 발급/인터뷰다.
