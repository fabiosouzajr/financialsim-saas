import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import Settings


def _svc_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="test-secret",
    )


@pytest.fixture
async def seed(session: AsyncSession):
    uid = uuid.uuid4().hex[:8]
    t = Tenant(name=f"Auth EP {uid}", slug=f"auth-ep-{uid}")
    session.add(t)
    await session.flush()
    email = f"ep-{uid}@test.com"
    svc = AuthService(session, _svc_settings())
    user = await svc.register_user(
        tenant_id=t.id, email=email, password="pass123",
        name="EP User", role=Role.admin,
    )
    await session.commit()
    return t, user, email


@pytest.mark.asyncio
async def test_login_returns_tokens(client, seed):
    _, _, email = seed
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access" in data and "refresh" in data


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, seed):
    _, _, email = seed
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client, seed):
    _, _, email = seed
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass123"}
    )
    r1 = login.json()["refresh"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh": r1})
    assert resp.status_code == 200
    assert resp.json()["refresh"] != r1


@pytest.mark.asyncio
async def test_refresh_reuse_returns_401(client, seed):
    _, _, email = seed
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass123"}
    )
    r1 = login.json()["refresh"]
    await client.post("/api/v1/auth/refresh", json={"refresh": r1})
    resp = await client.post("/api/v1/auth/refresh", json={"refresh": r1})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_returns_204(client, seed):
    _, _, email = seed
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass123"}
    )
    access = login.json()["access"]
    resp = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_password_reset_request_always_202(client, seed):
    _, _, email = seed
    for e in (email, "nobody@example.com"):
        resp = await client.post(
            "/api/v1/auth/password-reset/request", json={"email": e}
        )
        assert resp.status_code == 202
