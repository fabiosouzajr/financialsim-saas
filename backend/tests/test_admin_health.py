import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_admin(engine: AsyncEngine) -> str:
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"HealthTest-{uuid.uuid4().hex[:6]}", slug=f"ht-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id, email=f"h-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Health", role=Role.admin,
        )
        await session.flush()
        token, _ = await svc.issue_tokens(user)
        await session.commit()
    return token


@pytest.mark.asyncio
async def test_admin_health_returns_expected_shape(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_admin(engine)
    resp = await client.get(
        "/api/v1/admin/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "postgres" in data
    assert "redis" in data
    assert "providers" in data
    assert isinstance(data["providers"], dict)


@pytest.mark.asyncio
async def test_admin_health_non_admin_returns_403(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"HealthTest2-{uuid.uuid4().hex[:6]}", slug=f"ht2-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id, email=f"m-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Mgr", role=Role.manager,
        )
        await session.flush()
        token, _ = await svc.issue_tokens(user)
        await session.commit()

    resp = await client.get(
        "/api/v1/admin/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
