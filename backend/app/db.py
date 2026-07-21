"""async 엔진 / 세션 팩토리 및 FastAPI 의존성.

Supabase는 session pooler(5432)로 접속. transaction pooler(6543)를 써야 하면
create_async_engine 에 connect_args={"statement_cache_size": 0} 를 추가할 것.
(ARCHITECTURE.md §3-2, BACKEND.md §2)
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """요청 스코프 세션. 예외 시 롤백 후 재전파."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
