import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_with_rule(engine: AsyncEngine, role: Role = Role.admin) -> tuple[uuid.UUID, str]:
    from finacialsim_saas.cli.main import _seed_business_rules

    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"RuleTest-{role.value}", slug=f"rt-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        await _seed_business_rules(session, t.id)
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"u-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="User", role=role,
        )
        await session.flush()
        access_token, _ = await svc.issue_tokens(user)
        await session.commit()
        return t.id, access_token


@pytest.mark.asyncio
async def test_put_business_rule_updates_value(client: AsyncClient, engine: AsyncEngine):
    tenant_id, token = await _seed_with_rule(engine, Role.admin)

    resp = await client.put(
        "/api/v1/business-rules/entrada_minima_pct",
        json={"valor": "0.30"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Verify via GET
    resp2 = await client.get(
        "/api/v1/business-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp2.json()
    assert data["entrada_minima_pct"] == "0.30"


@pytest.mark.asyncio
async def test_put_business_rule_non_admin_forbidden(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_with_rule(engine, Role.manager)

    resp = await client.put(
        "/api/v1/business-rules/entrada_minima_pct",
        json={"valor": "0.40"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_business_rule_with_motivo(client: AsyncClient, engine: AsyncEngine):
    from finacialsim_saas.data.models import AuditLog
    from sqlalchemy import select

    tenant_id, token = await _seed_with_rule(engine, Role.admin)

    resp = await client.put(
        "/api/v1/business-rules/entrada_minima_pct",
        json={"valor": "0.25", "motivo": "Campanha"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    factory = build_session_factory(engine)
    async with factory() as s:
        logs = (await s.scalars(
            select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        )).all()
    assert len(logs) == 1
    assert logs[0].diff_json["motivo"] == "Campanha"
