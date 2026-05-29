import asyncio
import os
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from finacialsim_saas.data.database import Base, build_session_factory


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
    """Sync fixture: creates schema synchronously so no event-loop is captured."""
    eng = create_async_engine(db_url, poolclass=NullPool)

    async def _create_schema() -> None:
        async with eng.begin() as conn:
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
