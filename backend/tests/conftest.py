"""테스트 공용 픽스처.

DB 테스트는 로컬 docker postgres 대상(docker-compose.dev.yml). sqlite 대체 금지(pgvector).
각 테스트는 하나의 외부 트랜잭션 안에서 돌고 끝나면 롤백하므로 DB에 잔여 데이터가 남지 않는다.
라우터 코드가 db.commit() 을 호출해도 join_transaction_mode="create_savepoint" 덕분에
SAVEPOINT 해제로만 처리되어 외부 롤백이 유지된다.

주의: pytest-asyncio 는 테스트마다 새 이벤트 루프를 만든다. asyncpg 커넥션은 생성된
루프에 묶이므로 app.db 의 전역 엔진(커넥션 풀)을 공유하면 두 번째 테스트부터
"Event loop is closed" 가 난다 → 테스트마다 NullPool 엔진을 새로 만든다.
(BACKEND.md §11)
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import jwt
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """외부 트랜잭션에 묶인 세션. 테스트 종료 시 무조건 롤백."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:  # IntegrityError 등으로 이미 끝났으면 skip
            await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def tx_sessionmaker():
    """단일 커넥션/외부 트랜잭션에 묶인 async_sessionmaker.

    worker 테스트용: run_crawl_job 이 세션을 여러 번 열고 commit 해도, savepoint 모드라
    외부 트랜잭션 롤백으로 전부 정리된다. 주의 — 이 maker 로 만든 세션은 동시에 2개
    열지 말 것(같은 커넥션 공유). 테스트에서 순차적으로만 사용한다.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    conn = await engine.connect()
    trans = await conn.begin()
    maker = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield maker
    finally:
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """FastAPI 앱을 ASGI 로 직접 호출하는 테스트 클라이언트. get_db 를 테스트 세션으로 대체."""
    from app.db import get_db
    from app.main import app

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def auth_headers(user_id: UUID) -> dict[str, str]:
    """dev secret 으로 서명한 Supabase 형식 JWT 헤더."""
    token = jwt.encode(
        {
            "sub": str(user_id),
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "iat": datetime.now(UTC),
        },
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
