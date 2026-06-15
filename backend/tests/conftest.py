import asyncio
import os
from pathlib import Path
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

    # Stamp alembic to head so `alembic upgrade head` in CLI tests is a no-op
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command
    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option(
        "script_location",
        str(Path(__file__).parent.parent / "alembic"),
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("+asyncpg", ""))
    alembic_command.stamp(alembic_cfg, "head")

    yield eng
    asyncio.run(eng.dispose())


@pytest.fixture
def session_factory(engine: AsyncEngine, redis_url: str):
    """Returns a callable async session factory backed by the test engine.
    Depends on redis_url to ensure REDIS_URL env var is set before any test runs."""
    return build_session_factory(engine)


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
    url = f"redis://{host}:{port}"
    os.environ["REDIS_URL"] = url
    return url


@pytest_asyncio.fixture(autouse=True)
async def _clear_drain_lock(redis_url: str) -> None:
    """Delete the drain-outbox Redis lock before each test so tests don't skip each other."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url, decode_responses=True)
    await r.delete("lock:drain_notifications_outbox")
    await r.aclose()


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
    app.state.arq = AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
