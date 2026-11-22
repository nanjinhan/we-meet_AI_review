"""FastAPI 앱 진입점.

데이터 라우터는 prefix="/api/v1" 로 등록한다 (TECH_SPEC §7). /healthz 는 prefix 없이 유지.
(ARCHITECTURE.md §2)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    actions,
    assistant,
    auth,
    compare,
    dashboard,
    insights,
    internal,
    replies,
    reports,
    reviews,
    stores,
)

app = FastAPI(title="리뷰 진단 AI SaaS", version="0.1.0")

# 프론트(Vercel)에서의 크로스오리진 호출 허용. FRONTEND_ORIGINS(콤마 구분)로 배포 도메인으로
# 좁힌다 — 기본값 "*"(로컬 전체 허용)일 때만 와일드카드를 쓴다. "*"와 allow_credentials=True는
# 브라우저가 동시에 허용하지 않으므로(CORS 스펙), 그 경우는 credentials를 끈다 (T-15).
# .env 에 'FRONTEND_ORIGINS=' 처럼 값 없이 둔 경우도 미설정으로 보고 전체 허용한다 — 빈 목록이 되면
# 로컬 프론트(localhost:3000)의 모든 호출이 CORS 로 막힌다.
origins = [o.strip() for o in settings.frontend_origins.split(",") if o.strip()] or ["*"]
is_wildcard = origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=not is_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(stores.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(replies.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(compare.router, prefix="/api/v1")
app.include_router(insights.router, prefix="/api/v1")
app.include_router(actions.router, prefix="/api/v1")
app.include_router(assistant.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(internal.router)  # /internal/* — prefix 없이 (관리자 키 인증)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
