import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_user_with_tenant(engine: AsyncEngine, role: Role) -> tuple[str, uuid.UUID]:
    """Seed a user+tenant and return (access_token, tenant_id)."""
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(
            name=f"ProfileTest-{uuid.uuid4().hex[:6]}",
            slug=f"pft-{uuid.uuid4().hex[:6]}",
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
        return access_token, t.id


@pytest_asyncio.fixture
async def client_admin(engine: AsyncEngine):
    """AsyncClient pre-authenticated as an admin user."""
    from finacialsim_saas.main import app, app_state

    token, _tenant_id = await _seed_user_with_tenant(engine, Role.admin)
    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.redis = AsyncMock()
    app.state.arq = AsyncMock()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


@pytest_asyncio.fixture
async def client_user(engine: AsyncEngine):
    """AsyncClient pre-authenticated as a regular user (role=user)."""
    from finacialsim_saas.main import app, app_state

    token, _tenant_id = await _seed_user_with_tenant(engine, Role.user)
    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.redis = AsyncMock()
    app.state.arq = AsyncMock()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


# Valid CNPJ: 11.222.333/0001-81 (passes modulo-11 checksum)
_VALID_CNPJ = "11.222.333/0001-81"


@pytest.mark.asyncio
async def test_get_tenant_profile_returns_defaults(client_admin):
    """GET /admin/tenant-profile returns tenant fields; proposta_validade_dias defaults to 15."""
    r = await client_admin.get("/api/v1/admin/tenant-profile")
    assert r.status_code == 200
    body = r.json()
    assert "nome" in body
    assert body["proposta_validade_dias"] == 15
    assert body["cnpj"] is None
    assert body["logo_url"] is None


@pytest.mark.asyncio
async def test_put_tenant_profile_updates_fields(client_admin):
    """PUT /admin/tenant-profile updates name and validade_dias."""
    r = await client_admin.put(
        "/api/v1/admin/tenant-profile",
        json={
            "nome": "Minha Loja Atualizada",
            "cnpj": _VALID_CNPJ,
            "telefone": "11 99999-0000",
            "endereco": "Rua Nova, 456",
            "proposta_validade_dias": 20,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nome"] == "Minha Loja Atualizada"
    assert body["cnpj"] == _VALID_CNPJ
    assert body["proposta_validade_dias"] == 20

    # Verify persisted
    r2 = await client_admin.get("/api/v1/admin/tenant-profile")
    assert r2.json()["nome"] == "Minha Loja Atualizada"


@pytest.mark.asyncio
async def test_put_tenant_profile_rejects_invalid_cnpj(client_admin):
    """PUT rejects a CNPJ that fails the checksum validation."""
    r = await client_admin.put(
        "/api/v1/admin/tenant-profile",
        json={"nome": "Loja", "cnpj": "00.000.000/0000-00", "proposta_validade_dias": 15},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_put_tenant_profile_rejects_validade_over_30(client_admin):
    """PUT rejects proposta_validade_dias > 30."""
    r = await client_admin.put(
        "/api/v1/admin/tenant-profile",
        json={"nome": "Loja", "proposta_validade_dias": 31},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_logo_stores_and_returns_url(client_admin, tmp_path, monkeypatch):
    """POST /admin/tenant-profile/logo stores the file and returns a logo_url."""
    # Point storage at a temp dir so the upload actually succeeds
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path))

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal valid-ish PNG
    r = await client_admin.post(
        "/api/v1/admin/tenant-profile/logo",
        files={"file": ("logo.png", png_bytes, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["logo_url"] is not None


@pytest.mark.asyncio
async def test_post_logo_rejects_oversized_file(client_admin):
    """POST /admin/tenant-profile/logo rejects files > 2MB."""
    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 1)
    r = await client_admin.post(
        "/api/v1/admin/tenant-profile/logo",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_logo_rejects_non_image(client_admin):
    """POST /admin/tenant-profile/logo rejects non-image content type."""
    r = await client_admin.post(
        "/api/v1/admin/tenant-profile/logo",
        files={"file": ("doc.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_profile_requires_admin(client_user):
    """Non-admin users get 403 from tenant profile endpoints."""
    r = await client_user.get("/api/v1/admin/tenant-profile")
    assert r.status_code == 403
