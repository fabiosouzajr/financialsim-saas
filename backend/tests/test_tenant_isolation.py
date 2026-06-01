"""
Verifies that tenant A users cannot read tenant B's resources under any role.
Tests app-level tenant_id filtering (no RLS in Phase 1).
"""
import uuid
import pytest

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import Settings

_ROLES = [Role.admin, Role.manager, Role.user]


def _ss() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="test-secret",
    )


@pytest.fixture(scope="module")
async def two_tenants(engine):
    from finacialsim_saas.data.database import build_session_factory
    factory = build_session_factory(engine)
    tag = uuid.uuid4().hex[:6]
    async with factory() as session:
        ta = Tenant(name="Tenant A", slug=f"tenant-a-{tag}")
        tb = Tenant(name="Tenant B", slug=f"tenant-b-{tag}")
        session.add_all([ta, tb])
        await session.flush()

        svc = AuthService(session, _ss())
        users_a = {}
        users_b = {}
        for r in _ROLES:
            ua = await svc.register_user(
                tenant_id=ta.id, email=f"{r.value}_a_{tag}@iso.com",
                password="pass", name=f"{r.value} A", role=r,
            )
            ub = await svc.register_user(
                tenant_id=tb.id, email=f"{r.value}_b_{tag}@iso.com",
                password="pass", name=f"{r.value} B", role=r,
            )
            users_a[r] = ua
            users_b[r] = ub
        await session.commit()
        yield ta, tb, users_a, users_b, tag


@pytest.mark.asyncio
@pytest.mark.parametrize("role", _ROLES)
async def test_get_users_returns_only_own_tenant(client, two_tenants, role):
    ta, tb, users_a, users_b, tag = two_tenants
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"{role.value}_a_{tag}@iso.com", "password": "pass"},
    )
    assert login.status_code == 200, f"Login failed: {login.json()}"
    token = login.json()["access"]

    if role != Role.admin:
        # Non-admin gets 403 on /users
        resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        return

    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert all(f"_a_{tag}@iso.com" in e for e in emails)
    assert not any(f"_b_{tag}@iso.com" in e for e in emails)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", _ROLES)
async def test_get_me_returns_own_tenant(client, two_tenants, role):
    ta, tb, users_a, users_b, tag = two_tenants
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"{role.value}_a_{tag}@iso.com", "password": "pass"},
    )
    token = login.json()["access"]
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == str(ta.id)


@pytest.mark.asyncio
async def test_patch_user_cross_tenant_returns_403_or_404(client, two_tenants):
    ta, tb, users_a, users_b, tag = two_tenants
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"admin_a_{tag}@iso.com", "password": "pass"},
    )
    token = login.json()["access"]
    resp = await client.patch(
        f"/api/v1/users/{users_b[Role.user].id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"},
    )
    assert resp.status_code in (403, 404)
