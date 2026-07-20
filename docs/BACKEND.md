# BACKEND — FastAPI + 워커 구현 지침

> 대상: `backend/`. 모듈 단위로 "무엇을, 어떤 시그니처로" 만들지 명세한다.
> 코드 예시는 그대로 써도 되는 골격이다. 라우터는 얇게, 로직은 `services/`와 `pipeline/`에.

## 0. 의존성 (pyproject.toml)

```
fastapi, uvicorn[standard], pydantic-settings, sqlalchemy[asyncio]>=2.0, asyncpg,
pgvector (sqlalchemy용), anthropic, PyJWT, httpx, apscheduler, playwright,
pywebpush, FlagEmbedding (BGE-M3), python-multipart, pyyaml
dev: pytest, pytest-asyncio, ruff, aiosqlite(금지-postgres로만 테스트), testcontainers[postgres](선택)
```

## 1. config.py — 설정

`pydantic-settings`의 `BaseSettings` 하나로 모든 env를 모은다. 다른 모듈에서 `os.environ` 직접 접근 금지.

```python
class Settings(BaseSettings):
    database_url: str                    # postgresql+asyncpg://... (Supabase session pooler 5432)
    supabase_jwt_secret: str
    anthropic_api_key: str
    llm_model_classify: str = "claude-haiku-4-5"
    llm_model_generate: str = "claude-sonnet-5"
    kakao_rest_api_key: str = ""
    kakao_redirect_uri: str = ""
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    internal_api_key: str                # /internal/* 보호용
    snapshot_dir: str = "/data/snapshots"
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
```

## 2. db.py / models.py

- `db.py`: `create_async_engine(settings.database_url, pool_size=5, pool_pre_ping=True)`,
  `async_sessionmaker`, FastAPI 의존성 `get_db()` (yield 세션, 예외 시 rollback).
- `models.py`: `docs/schema.sql`과 1:1 매핑되는 SQLAlchemy 2.0 `Mapped[...]` 스타일 모델.
  pgvector 컬럼은 `pgvector.sqlalchemy.Vector(1024)`.
- **스키마의 원본은 SQL 파일이다.** 모델을 바꾸면 반드시 `migrations/NNN_*.sql`도 추가.

## 3. deps.py — 인증·소유권

```python
async def get_current_user(authorization: str = Header(...)) -> UUID:
    """Bearer 토큰에서 Supabase JWT 검증 후 user id(sub) 반환. 실패 시 401."""
    token = authorization.removeprefix("Bearer ").strip()
    payload = jwt.decode(token, settings.supabase_jwt_secret,
                         algorithms=["HS256"], audience="authenticated")
    return UUID(payload["sub"])

async def get_owned_store(store_id: int, user=Depends(get_current_user),
                          db=Depends(get_db)) -> Store:
    """store.owner_id == user 검사. 아니면 404(존재 은닉)."""

async def require_internal_key(x_internal_key: str = Header(...)):
    """/internal/* 전용. settings.internal_api_key와 비교."""
```

모든 데이터 라우터는 `get_owned_store`를 통과해야 한다. review/reply 단건 접근도
join으로 소유 매장인지 검사하는 헬퍼(`get_owned_review`, `get_owned_reply`)를 만들어 쓴다.

## 4. llm/ — 유일한 LLM 게이트웨이

### llm/schemas.py — LLM 출력 Pydantic 모델 (전부 여기에)

```python
class AspectItem(BaseModel):
    category: Literal["맛","친절","청결","대기시간","가격","분위기","기타"]
    polarity: Literal["pos","neg"]

class ReviewAnalysisOut(BaseModel):
    review_index: int                       # 배치 내 인덱스로 매핑
    sentiment: Literal["pos","neu","neg"]
    severity: Literal["normal","uncomfortable","complaint","malicious"]
    urgent: bool                            # 위생/이물/환불/법적 언급
    aspects: list[AspectItem]
    keywords: list[str]

class BatchAnalysisOut(BaseModel):
    results: list[ReviewAnalysisOut]

class ReplyOut(BaseModel):
    draft: str                              # 150자 내외

class RouterDecision(BaseModel):
    intent: Literal["stats","evidence","both","chitchat"]
    aspect: str | None = None
    sentiment: Literal["pos","neg"] | None = None
    period_weeks: int = 4                   # 최근 N주
    query_text: str | None = None           # evidence용 검색 문장

class Diagnosis(BaseModel):
    level: Literal["crit","warn","strength","opportunity"]
    title: str
    evidence: str                           # 반드시 프롬프트에 준 수치만 인용
class Prescription(BaseModel):
    title: str; detail: str; expected_effect: str
class WeeklyReportOut(BaseModel):
    diagnosis: list[Diagnosis]
    prescriptions: list[Prescription]
```

### llm/client.py — 호출 규약

```python
from anthropic import AsyncAnthropic
_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

def load_prompt(name: str, **vars) -> str:
    """backend/prompts/{name}.md 를 읽어 {var} 치환. 파일 없으면 즉시 에러."""

async def generate(prompt_name: str, variables: dict, output_model: type[BaseModel],
                   model: str | None = None, max_tokens: int = 4096) -> BaseModel:
    """structured outputs로 스키마 보장. API 오류 시 1회 재시도 후 예외 전파.
    호출·토큰 사용량을 JSON 로그로 남긴다(비용 추적)."""
    resp = await _client.messages.parse(
        model=model or settings.llm_model_generate,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": load_prompt(prompt_name, **variables)}],
        output_format=output_model,
    )
    return resp.parsed_output

async def generate_stream(prompt_name, variables, model=None):
    """비서 최종 답변용 텍스트 스트리밍(스키마 없음). async generator of str."""
```

- 분류 호출은 `model=settings.llm_model_classify`(Haiku), 생성은 기본값(Sonnet 5).
- **다른 모듈에서 anthropic import 금지.** 벤더 교체 시 이 파일만 수정.
- 프롬프트 파일: `classify_v1.md`, `reply_v1.md`, `report_v1.md`,
  `assistant_router_v1.md`, `assistant_answer_v1.md`. 가드레일(보상 약속 금지,
  집계값만 인용 등)은 프롬프트 파일 안에 명시한다.

## 5. collectors/ — 수집기

### base.py
```python
class RawReview(BaseModel):
    author_display: str      # 저장 전 마스킹됨 — collector 밖으로 원문 유출 금지
    rating: int | None
    body: str
    visited_at: date | None

class BaseCollector(ABC):
    @abstractmethod
    async def collect(self, channel: StoreChannel, stop_after_known: int = 2
                      ) -> list[RawReview]: ...

def dedup_key(r: RawReview) -> str:  # sha1(author+visited+body[:50])
def mask_author(name: str) -> str:   # '김철수' -> '김**'
```

### naver.py (최대 리스크 — 방어적으로)
- Playwright headless Chromium, **인스턴스 1개 순차 처리**. 모바일 웹 리뷰 페이지 대상.
- 셀렉터는 `selectors.yaml`에서 로딩:
  ```yaml
  naver:
    review_item: "..."
    author: "..."
    body: "..."
    rating: "..."
    visited_at: "..."
    more_button: "..."
  ```
- 증분수집: 최신순으로 읽다가 이미 저장된 dedup_key를 2페이지 연속 만나면 중단.
- 실패 시 지수 백오프(5분→30분→2시간)는 worker 스케줄 레벨에서 처리. collector는 예외만 던진다.
- 페이지 HTML을 `{snapshot_dir}/{channel_id}/{ts}.html`로 저장, 7일 지난 파일 삭제.
- **0건 수집이 2회 연속이면** `services/`에 기록 → 관리자 카카오 알림 ("구조 변경 의심").

### csv_import.py
`작성일,별점,본문` 3컬럼(+선택 작성자). `POST /stores/{id}/reviews:import`에서 사용.
파싱 실패 행은 건너뛰고 `{imported, skipped}` 반환.

## 6. pipeline/ — 분석 파이프라인 (worker와 api 양쪽에서 호출됨)

| 파일 | 함수 | 내용 |
|---|---|---|
| analyze.py | `analyze_new_reviews(db, channel_id)` | 미분석 리뷰 조회 → 15건씩 배치로 `generate("classify_v1", ..., BatchAnalysisOut, model=classify)` → review_analysis insert. 실패 배치는 `model_ver='failed'` 마킹 후 계속(전체 중단 금지) → stats upsert → urgent/저평점이면 notify.dispatch 호출 → embed 호출 |
| embed.py | `embed_reviews(db, review_ids)` | BGE-M3 (FlagEmbedding, CPU). 모델은 프로세스 시작 시 1회 로딩(전역 lazy singleton) |
| stats.py | `upsert_week_stats(db, store_id, week_start)` | review_analysis에서 해당 주 재집계 → weekly_aspect_stats UPSERT. aspect별 + '전체' row |
| reply_gen.py | `generate_reply(db, review_id, tone)` | 리뷰+분석+store_settings.tone_examples(few-shot) → `generate("reply_v1", ..., ReplyOut)` → replies insert(draft) |
| report_gen.py | `generate_weekly_report(db, store_id, week_start)` | 4주치 통계+급증 키워드+경쟁 통계 → `generate("report_v1", ..., WeeklyReportOut)` → **수치 검증**: diagnosis.evidence 안의 숫자가 프롬프트에 넣은 집계값 집합에 없으면 1회 재생성, 재실패 시 해당 항목 제거 → reports insert |

경쟁매장 채널(is_competitor=true)은 analyze/embed/stats까지만 수행. reply/알림 생성 금지.

## 7. notify/ — 알림

- `kakao.py`: 나에게 보내기(`/v2/api/talk/memo/default/send`, httpx). `kakao_tokens`에서
  토큰 로드, 만료 시 refresh 후 저장. 온보딩 라우터(`/auth/kakao/callback`)에서 토큰 최초 저장.
- `webpush.py`: `pywebpush`로 push_subscriptions 전체 기기에 발송. 410 Gone이면 구독 삭제.
- `dispatch.py`: `send_urgent(store, review)`, `send_digest(store, reviews)`,
  `send_report_ready(store)` — 채널 선택 + alerts 테이블 로깅을 여기서 일원화.

## 8. worker.py — 스케줄러 (별도 프로세스)

```python
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
# 1) 매장별 크롤: 09:00 / 21:00 + random jitter(0~30분). 채널 순차 처리(병렬 금지)
# 2) crawl_jobs 폴링: 10초 간격, pending → running → collector 실행 → done/failed
# 3) 알림 다이제스트: 매시 정각, 미발송 일반 부정 리뷰 묶음 발송
# 4) 주간 리포트: 월 07:00, 전 매장 report_gen 실행
# 5) 스냅샷 청소: 일 1회, 7일 지난 HTML 삭제
# 크롤 실패 시 백오프 재시도(5분→30분→2시간, 3회 후 포기)는 job 내부에서 처리
```

worker는 api와 같은 DB를 쓰지만 **FastAPI 앱을 import하지 않는다** (pipeline/collectors/notify만).

## 9. routers/ — 엔드포인트 (스펙 §7과 1:1)

| 파일 | 엔드포인트 | 비고 |
|---|---|---|
| stores.py | `POST /stores`, `GET /stores`, `GET /stores/{id}`, `PUT /stores/{id}/settings` | 생성 시 store_settings row도 생성 |
| stores.py | `POST /stores/{id}/channels` | 등록 직후 crawl_jobs insert(첫 수집 트리거) |
| reviews.py | `GET /stores/{id}/reviews` | 필터: sentiment/urgent/answered, 커서 페이지네이션(`?cursor=<id>&limit=20`, id desc) |
| reviews.py | `POST /stores/{id}/reviews:import` | CSV 폴백. 업로드 후 BackgroundTasks로 analyze 실행 |
| replies.py | `POST /reviews/{id}/reply:generate` `{tone}` | 동기 호출(수 초). 기존 draft 있으면 discard 후 재생성 |
| replies.py | `POST /replies/{id}:approve` | status='approved' + approved_at. 응답에 draft 포함(프론트가 클립보드 복사) |
| dashboard.py | `GET /stores/{id}/dashboard?range=4w` | weekly_aspect_stats만 읽기. 종합점수 = `100*(0.5*긍정비율 + 0.3*평점/5 + 0.2*답변율)` — 가중치는 `services/score.py` 상수 |
| reports.py | `GET /stores/{id}/reports/latest`, `GET /stores/{id}/reports/{report_id}` | |
| compare.py | `GET /stores/{id}/compare` | 우리 vs 경쟁 aspect 통계 + 한 줄 인사이트(리포트 생성 시 캐시된 것 재사용) |
| assistant.py | `POST /stores/{id}/assistant/messages` | SSE(StreamingResponse, `text/event-stream`). 흐름은 ARCHITECTURE §4. `GET .../messages` 로 히스토리 |
| internal.py | `POST /internal/crawl:trigger` | require_internal_key. crawl_jobs insert |
| auth.py | `GET /auth/kakao/callback`, `POST /push/subscribe` | 카카오 토큰 저장 / 웹푸시 구독 저장 |

## 10. services/assistant_queries.py — 비서 쿼리 템플릿

자유 SQL 금지. 아래 함수만 존재하고, 라우터 결과(RouterDecision)의 파라미터를 바인딩한다:

```python
async def top_problem_aspects(db, store_id, weeks) -> list[dict]     # neg_cnt 상위
async def aspect_trend(db, store_id, aspect, weeks) -> list[dict]    # 주별 추이
async def compare_period(db, store_id, aspect, weeks) -> dict        # 전기간 대비 증감률
async def search_evidence(db, store_id, query_text, sentiment, weeks, k=5) -> list[Review]
    # BGE-M3로 query_text 임베딩 → pgvector cosine 검색 + written_at/sentiment 필터
```

## 11. 테스트 방침

- 단위: dedup_key/mask_author, score 산식, stats upsert, 리포트 수치 검증 로직.
- LLM은 `llm.client.generate`를 monkeypatch — 실제 API 호출하는 테스트 금지.
- collector는 저장된 HTML 스냅샷 픽스처로 파싱만 테스트(라이브 크롤 테스트 금지).
- DB 테스트는 로컬 docker postgres 대상(`docker-compose.dev.yml`). sqlite 대체 금지(pgvector).
