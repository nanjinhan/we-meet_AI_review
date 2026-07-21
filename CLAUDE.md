# 리뷰 진단 AI SaaS — 프로젝트 규약

네이버 플레이스 리뷰를 수집·분석해 소상공인에게 알림/AI답글/리포트/비교/AI비서를 제공하는 B2B SaaS.
3인 학생 팀, 12주 MVP. **요구사항의 원천은 `docs/TECH_SPEC.md`** — 스펙과 충돌하는 구현을 하지 말 것.

## 문서 맵 (작업 전 반드시 해당 문서를 읽을 것)

| 문서 | 내용 |
|---|---|
| `docs/TECH_SPEC.md` | 제품 요구사항·범위·일정 (수정 금지, 읽기 전용) |
| `docs/ARCHITECTURE.md` | 시스템 구조, 저장소 레이아웃, 기술 결정과 이유 |
| `docs/schema.sql` | DB 스키마 전체 (마이그레이션의 원본) |
| `docs/BACKEND.md` | FastAPI + 워커 구현 지침 (모듈별 명세) |
| `docs/FRONTEND.md` | Next.js PWA 구현 지침 |
| `docs/TASKS.md` | 작업 단위 목록 — 작업 지시가 모호하면 여기서 해당 태스크를 찾아 수행 |

## 핵심 규칙 (위반 금지)

1. **오버엔지니어링 금지.** Celery·Redis·메시지큐·MSA·캐시서버 도입 금지. 모놀리스 FastAPI + 워커 1개.
2. **LLM 호출은 `backend/app/llm/client.py`를 통해서만.** 다른 파일에서 anthropic SDK를 직접 import 하지 말 것.
3. **프롬프트는 코드에 하드코딩하지 말고 `backend/prompts/*.md`에 버전 붙여 저장.**
4. **LLM 출력은 전부 Pydantic 모델로 스키마 강제** (structured outputs). 자유 텍스트 파싱 금지.
5. **크롤러 CSS 셀렉터는 `backend/selectors.yaml`에만.** 파이썬 코드에 셀렉터 문자열 금지.
6. **AI 비서에서 자유 Text-to-SQL 금지.** 사전 정의된 쿼리 템플릿 + 파라미터 바인딩만.
7. **서버가 네이버에 자동 게시하는 코드 작성 금지.** 답글은 승인 → 클립보드 복사(프론트) 반자동만.
8. **모든 데이터 API는 소유권 검사** (`store.owner_id == jwt.sub`) 필수. 프론트는 Supabase를 Auth 용도로만 쓰고, 데이터는 전부 FastAPI 경유.
9. **DB 스키마 변경은 `backend/migrations/`에 새 SQL 파일 추가** + `docs/schema.sql` 동기화. 기존 마이그레이션 파일 수정 금지.
10. 시크릿은 `.env`로만. 코드/레포에 키 커밋 금지.

## 스택 요약

- 백엔드: Python 3.12, FastAPI, SQLAlchemy 2.0(async)+asyncpg, APScheduler(워커), Playwright
- DB/Auth: Supabase (PostgreSQL 15 + pgvector + Auth). 로컬 개발은 docker postgres
- LLM: Anthropic API — 분류 `claude-haiku-4-5`, 생성(답글·리포트·비서) `claude-sonnet-5` (env로 오버라이드 가능)
- 임베딩: BGE-M3 로컬 CPU (1024차원)
- 프론트: Next.js 15(App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + Serwist(PWA)

## 명령어

- 백엔드 실행: `cd backend && uvicorn app.main:app --reload`
- 워커 실행: `cd backend && python -m app.worker`
- 테스트: `cd backend && pytest`
- 프론트: `cd frontend && npm run dev`
- 로컬 DB: `docker compose -f docker-compose.dev.yml up -d`
