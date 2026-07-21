"""FastAPI 앱 진입점.

데이터 라우터는 prefix="/api/v1" 로 등록한다 (TECH_SPEC §7). /healthz 는 prefix 없이 유지.
(ARCHITECTURE.md §2)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, internal, replies, reviews, stores

app = FastAPI(title="리뷰 진단 AI SaaS", version="0.1.0")

# 프론트(Vercel)에서의 크로스오리진 호출 허용. 배포 시 도메인으로 좁힌다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(stores.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(replies.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(internal.router)  # /internal/* — prefix 없이 (관리자 키 인증)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}
