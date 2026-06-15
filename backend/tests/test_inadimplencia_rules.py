import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_tenant(engine: AsyncEngine) -> tuple[uuid.UUID, str]:
    from finacialsim_saas.cli.main import _seed_business_rules

    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"InadTest-{uuid.uuid4().hex[:6]}", slug=f"inad-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        await _seed_business_rules(session, t.id)
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id, email=f"u-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Admin", role=Role.admin,
        )
        await session.flush()
        token, _ = await svc.issue_tokens(user)
        await session.commit()
        return t.id, token


@pytest.mark.asyncio
async def test_multa_pct_above_ceiling_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_multa_pct",
        json={"valor": "2.01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_juros_pct_above_ceiling_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_juros_diario_pct",
        json={"valor": "0.11"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_carencia_dias_above_ceiling_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_carencia_dias",
        json={"valor": 31},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_valid_multa_pct_accepted(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_multa_pct",
        json={"valor": "2.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_negative_multa_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_multa_pct",
        json={"valor": "-0.01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_business_rules_get_includes_inadimplencia_defaults(
    client: AsyncClient, engine: AsyncEngine
):
    _, token = await _seed_tenant(engine)
    resp = await client.get(
        "/api/v1/business-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inadimplencia_multa_pct"] == "0.00"
    assert data["inadimplencia_juros_diario_pct"] == "0.00"
    assert data["inadimplencia_carencia_dias"] == 0
