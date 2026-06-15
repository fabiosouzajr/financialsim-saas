"""Smoke tests for portal API — full isolation tests are in test_portal_endpoints.py (Plan 6E)."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_portal_me_requires_customer_role(client: AsyncClient):
    """Without auth, /portal/me returns 401."""
    r = await client.get("/api/v1/portal/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_portal_me_staff_gets_403(client: AsyncClient, session: AsyncSession):
    """A real admin user's JWT accessing /portal/me gets 403 (wrong role, not unknown user)."""
    import jwt
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.data.models import Role, Tenant
    from finacialsim_saas.settings import get_settings

    cfg = get_settings()
    tenant = Tenant(name="PortalSmoke", slug=f"portal-smoke-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    svc = AuthService(session, cfg)
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"smoke-{uuid.uuid4().hex[:6]}@test.com",
        password="pw", name="Admin", role=Role.admin,
    )
    await session.commit()

    token = jwt.encode(
        {"sub": str(admin.id), "tenant_id": str(tenant.id),
         "role": "admin", "iat": 0, "exp": 9999999999},
        cfg.jwt_secret_key, algorithm="HS256",
    )
    r = await client.get(
        "/api/v1/portal/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_webhook_pix_always_200(client: AsyncClient):
    """Webhook endpoint always returns 200 regardless of payload."""
    r = await client.post(
        "/api/v1/webhooks/pix",
        content=b'{"pix": []}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
