import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


@pytest_asyncio.fixture(autouse=True)
async def clean_settings(engine: AsyncEngine):
    """Truncate system_settings before each test to ensure isolation."""
    factory = build_session_factory(engine)
    async with factory() as session:
        await session.execute(text("DELETE FROM system_settings"))
        await session.commit()
    yield


async def _seed_user(engine: AsyncEngine, role: Role) -> str:
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(
            name=f"AdminSettingsTest-{uuid.uuid4().hex[:6]}",
            slug=f"ast-{uuid.uuid4().hex[:6]}",
        )
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"u-{uuid.uuid4().hex[:6]}@test.com",
            password="pw",
            name="Test",
            role=role,
        )
        await session.flush()
        access_token, _ = await svc.issue_tokens(user)
        await session.commit()
    return access_token


@pytest.mark.asyncio
async def test_get_settings_returns_env_defaults(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.get(
        "/api/v1/admin/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "smtp_host" in data
    assert data["smtp_host"]["source"] == "env"
    assert "pix_provider" in data
    assert data["pix_provider"]["source"] == "env"


@pytest.mark.asyncio
async def test_put_get_round_trip(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.put(
        "/api/v1/admin/settings/smtp_host",
        json={"value": "mail.example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    resp2 = await client.get(
        "/api/v1/admin/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp2.json()
    assert data["smtp_host"]["value"] == "mail.example.com"
    assert data["smtp_host"]["source"] == "db"


@pytest.mark.asyncio
async def test_put_non_admin_returns_403(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.manager)
    resp = await client.put(
        "/api/v1/admin/settings/smtp_host",
        json={"value": "mail.example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_readonly_key_returns_422(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.put(
        "/api/v1/admin/settings/pix_provider",
        json={"value": "external"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_unknown_key_returns_422(client: AsyncClient, engine: AsyncEngine):
    token = await _seed_user(engine, Role.admin)
    resp = await client.put(
        "/api/v1/admin/settings/nonexistent_key",
        json={"value": "value"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
