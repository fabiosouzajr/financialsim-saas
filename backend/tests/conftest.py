import asyncio
import os
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from finacialsim_saas.data.database import Base, build_session_factory
import finacialsim_saas.data.models  # noqa: F401 — registers all ORM models with Base.metadata


# ── Postgres ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def postgres_container():
    """Starts a real Postgres 16 container for the test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container) -> str:
    url = postgres_container.get_connection_url()
    dsn = url.replace("psycopg2", "asyncpg").replace("postgresql://", "postgresql+asyncpg://")
    os.environ["DATABASE_URL"] = dsn
    return dsn


@pytest.fixture(scope="session")
def engine(db_url: str) -> AsyncEngine:
    """Sync fixture: enables citext extension, then creates schema."""
    from sqlalchemy import text as _text

    eng = create_async_engine(db_url, poolclass=NullPool)

    async def _create_schema() -> None:
        async with eng.begin() as conn:
            await conn.execute(_text("CREATE EXTENSION IF NOT EXISTS citext"))
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())
    yield eng
    asyncio.run(eng.dispose())


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    factory = build_session_factory(engine)
    async with factory() as s:
        yield s


# ── Redis ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def redis_container():
    """Starts a real Redis 7 container for the test session."""
    with RedisContainer("redis:7") as r:
        yield r


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


@pytest_asyncio.fixture
async def client(engine: AsyncEngine):
    """Shared HTTP test client. Bypasses lifespan — injects session_factory directly."""
    from unittest.mock import AsyncMock

    from httpx import ASGITransport, AsyncClient
    from finacialsim_saas.main import app, app_state
    from finacialsim_saas.data.database import build_session_factory

    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.redis = AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
