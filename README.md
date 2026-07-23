# 리뷰 진단 AI SaaS (we-meet)

네이버 플레이스 리뷰를 자동 수집·분석해 소상공인에게 **① 부정리뷰 즉시 알림 ② AI 답글 초안 ③ 진단·처방 리포트 ④ 경쟁매장 비교 ⑤ 자연어 AI 비서**를 제공하는 B2B SaaS.

> 3인 학생팀 · 12주 MVP · 요구사항 원천은 [`docs/TECH_SPEC.md`](docs/TECH_SPEC.md)

**진행 상황: 백엔드 T-01~T-14 + 프론트 T-F1 완료 · pytest 84개 통과** — 상세·다음 작업은 👉 [`이어서진행.md`](이어서진행.md)

---

## 스택

| 영역 | 사용 |
|---|---|
| 백엔드 | Python 3.12(목표) · FastAPI · SQLAlchemy 2.0 async + asyncpg · APScheduler · Playwright |
| DB | PostgreSQL 15 + pgvector (로컬은 docker) |
| LLM | **Google Gemini 무료 티어** (프로바이더 추상화 — `backend/app/llm/client.py` 한 파일만 의존) |
| 프론트 | Next.js 15 + TypeScript + Tailwind (스캐폴딩 단계) |

## 빠른 시작

```bash
# 1) DB
docker compose -f docker-compose.dev.yml up -d

# 2) 백엔드
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -e ".[dev]"
cp ../.env.example .env        # ★ 각자 GEMINI_API_KEY 발급해 넣기 → https://aistudio.google.com/apikey
uvicorn app.main:app --reload  # http://localhost:8000/healthz
pytest                         # 전체 테스트

# 3) 프론트
cd ../frontend && npm install && npm run dev
```

> 🔒 `.env`(특히 `GEMINI_API_KEY`)는 **커밋 금지**. 저장소엔 `.env.example`만 있고, 각자 자기 키를 로컬 `.env`에 넣는다.

## 저장소 구조

```
backend/
  app/
    main.py config.py db.py deps.py models.py   # 앱 기반 + 인증 + 모델
    collectors/   # 수집기 (base / csv_import / naver)
    pipeline/     # 분석 (analyze / stats / embed / reply_gen)
    llm/          # LLM 게이트웨이 (client / schemas) — 유일한 벤더 의존점
    notify/       # 알림 (kakao / webpush / dispatch)
    routers/      # API 엔드포인트
    worker.py     # APScheduler 워커 (크롤·분석·다이제스트)
  migrations/     # 001_init ~ 003 (SQL)
  prompts/        # LLM 프롬프트 (버전 관리)
  tests/          # pytest (docker postgres 대상, 외부 호출은 mock)
frontend/         # Next.js 15 PWA (예정: T-F1~F7)
docs/             # TECH_SPEC / ARCHITECTURE / BACKEND / FRONTEND / TASKS / schema.sql
이어서진행.md      # 진행 인수인계 문서 (여기부터 이어서 — 새 세션은 이거부터 읽기)
CLAUDE.md         # 프로젝트 규약 (10대 규칙)
```

## 작업 방식

- 작업 단위는 [`docs/TASKS.md`](docs/TASKS.md)의 T-01~T-15 / T-F1~T-F7.
- 모든 태스크 공통 완료 조건: `ruff check` 통과 · 관련 pytest 통과 · `CLAUDE.md` 규칙 준수.
- 이어서 작업하려면 [`이어서진행.md`](이어서진행.md)의 "다음 작업" 절부터.
