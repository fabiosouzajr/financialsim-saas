import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_staff(engine: AsyncEngine, role: Role = Role.admin) -> tuple[str, str]:
    """Returns (tenant_id_str, access_token)."""
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"ITest-{role.value}", slug=f"itest-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"staff-{uuid.uuid4().hex[:6]}@test.com",
            password="pw",
            name="Staff",
            role=role,
        )
        await session.flush()
        access_token, _ = await svc.issue_tokens(user)
        await session.commit()
        return str(t.id), access_token


async def _seed_indicator(engine: AsyncEngine, codigo: str = "SELIC") -> None:
    from finacialsim_saas.services.indicators_service import IndicatorsService
    from finacialsim_saas.integrations.bacen.schema import IndicatorPoint

    factory = build_session_factory(engine)
    async with factory() as s:
        svc = IndicatorsService(s)
        await svc.upsert(IndicatorPoint(
            codigo=codigo,
            data_referencia=date(2026, 6, 1),
            valor=Decimal("10.75"),
            unidade="pct_aa",
            fonte="bacen_sgs",
        ))
        await s.commit()


@pytest.mark.asyncio
async def test_list_indicators_returns_array(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_staff(engine)
    await _seed_indicator(engine, "SELIC")
    await _seed_indicator(engine, "CDI")

    resp = await client.get(
        "/api/v1/indicators", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    codigos = [d["codigo"] for d in data]
    assert "SELIC" in codigos


@pytest.mark.asyncio
async def test_indicator_series(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_staff(engine)
    await _seed_indicator(engine, "TX_BACEN_VEIC")

    resp = await client.get(
        "/api/v1/indicators/TX_BACEN_VEIC/series?range=12m",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "TX_BACEN_VEIC"
    assert isinstance(data["points"], list)


@pytest.mark.asyncio
async def test_refresh_indicators_requires_admin(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_staff(engine, role=Role.user)

    resp = await client.post(
        "/api/v1/indicators/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_indicators_as_admin_returns_202(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_staff(engine, role=Role.admin)

    resp = await client.post(
        "/api/v1/indicators/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202
    assert resp.json()["enqueued"] is True
