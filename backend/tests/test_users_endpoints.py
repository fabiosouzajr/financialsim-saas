import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import Settings


def _ss() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="test-secret",
    )


@pytest.fixture
async def setup(session: AsyncSession):
    tag = uuid.uuid4().hex[:6]
    admin_email = f"admin-{tag}@users.com"
    member_email = f"member-{tag}@users.com"
    t = Tenant(name="Users EP", slug=f"users-ep-{tag}")
    session.add(t)
    await session.flush()
    svc = AuthService(session, _ss())
    admin = await svc.register_user(
        tenant_id=t.id, email=admin_email, password="pass",
        name="Admin", role=Role.admin,
    )
    member = await svc.register_user(
        tenant_id=t.id, email=member_email, password="pass",
        name="Member", role=Role.user,
    )
    await session.commit()
    return t, admin, member, admin_email, member_email


async def _login(client, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass"}
    )
    return resp.json()["access"]


@pytest.mark.asyncio
async def test_get_me(client, setup):
    _, admin, _, admin_email, _ = setup
    token = await _login(client, admin_email)
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == admin_email
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_get_users_as_admin_returns_staff_only(client, setup):
    _, _, _, admin_email, member_email = setup
    token = await _login(client, admin_email)
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert admin_email in emails
    assert member_email in emails


@pytest.mark.asyncio
async def test_get_users_as_user_role_returns_403(client, setup):
    _, _, _, _, member_email = setup
    token = await _login(client, member_email)
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_users_creates_user(client, setup):
    t, _, _, admin_email, _ = setup
    tag = uuid.uuid4().hex[:6]
    token = await _login(client, admin_email)
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": f"new-{tag}@users.com", "name": "New", "password": "pw123", "role": "user"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_patch_user_role(client, setup):
    t, _, member, admin_email, _ = setup
    token = await _login(client, admin_email)
    resp = await client.patch(
        f"/api/v1/users/{member.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"


@pytest.mark.asyncio
async def test_get_me_unauthenticated_returns_401(client, setup):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
