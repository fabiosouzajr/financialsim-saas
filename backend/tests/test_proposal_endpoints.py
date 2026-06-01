"""Integration tests for proposal API endpoints."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import (
    AmortizationRow, Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.settings import get_settings


async def _seed_tenant_user_sim(engine: AsyncEngine) -> tuple[str, str]:
    """Seed a tenant + user + simulation; return (bearer_token, sim_id)."""
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name="TenantAPI", slug=f"api-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        email = f"v-{uuid.uuid4().hex[:8]}@test.com"
        user = await svc.register_user(
            tenant_id=t.id, email=email, name="Vend", password="pw123", role=Role.user
        )
        await s.flush()
        sim = Simulation(
            tenant_id=t.id,
            codigo=f"SIM-{uuid.uuid4().hex[:6]}",
            valor_veiculo=Decimal("85000.00"),
            valor_entrada=Decimal("17000.00"),
            valor_financiado=Decimal("68000.00"),
            taxa_mensal=Decimal("0.012900"),
            prazo_meses=48,
            data_liberacao=date(2026, 6, 1),
            primeiro_vencimento=date(2026, 7, 1),
            incluir_iof=True,
            iof_total=Decimal("1224.00"),
            parcela_financiamento=Decimal("1987.34"),
            total_pago=Decimal("95392.32"),
            total_juros=Decimal("27392.32"),
            cet_mensal=Decimal("0.013500"),
            cet_anual=Decimal("0.174500"),
            status=SimulationStatus.confirmado,
            rules_snapshot_json={},
            criado_por=user.id,
        )
        s.add(sim)
        await s.flush()
        for i in range(1, 4):
            s.add(AmortizationRow(
                simulation_id=sim.id, tenant_id=t.id,
                numero_parcela=i, data_vencimento=date(2026, 6 + i, 1),
                dias_periodo=30,
                saldo_anterior=Decimal("68000.00") - (i - 1) * Decimal("1110.14"),
                juros=Decimal("877.20"), amortizacao=Decimal("1110.14"),
                parcela=Decimal("1987.34"),
                saldo_devedor=Decimal("68000.00") - i * Decimal("1110.14"),
                extras_total=Decimal("0.00"), parcela_total=Decimal("1987.34"),
                ajuste_arredondamento=Decimal("0.00"),
            ))
        access_token, _ = await svc.issue_tokens(user)
        await s.commit()
        return access_token, str(sim.id)


@pytest.mark.asyncio
async def test_post_proposal_returns_202(client, engine):
    token, sim_id = await _seed_tenant_user_sim(engine)
    r = await client.post(
        "/api/v1/proposals",
        json={"simulation_id": sim_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["render_status"] == "pending"
    assert body["status"] == "rascunho"
    assert body["codigo"].startswith("PROP-")


@pytest.mark.asyncio
async def test_duplicate_proposal_returns_409(client, engine):
    token, sim_id = await _seed_tenant_user_sim(engine)
    headers = {"Authorization": f"Bearer {token}"}
    r1 = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    assert r1.status_code == 202
    r2 = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_404(client, engine):
    token_a, sim_a = await _seed_tenant_user_sim(engine)
    token_b, _ = await _seed_tenant_user_sim(engine)

    r = await client.post(
        "/api/v1/proposals",
        json={"simulation_id": sim_a},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 202
    proposal_id = r.json()["id"]

    r2 = await client.get(
        f"/api/v1/proposals/{proposal_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_get_proposal_returns_render_status(client, engine):
    token, sim_id = await _seed_tenant_user_sim(engine)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    assert r.status_code == 202
    proposal_id = r.json()["id"]

    r2 = await client.get(f"/api/v1/proposals/{proposal_id}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["render_status"] in ("pending", "rendering", "ready", "failed")


@pytest.mark.asyncio
async def test_approve_requires_ready_status(client, engine):
    token, sim_id = await _seed_tenant_user_sim(engine)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/proposals", json={"simulation_id": sim_id}, headers=headers)
    assert r.status_code == 202
    proposal_id = r.json()["id"]

    r2 = await client.post(f"/api/v1/proposals/{proposal_id}/approve", headers=headers)
    assert r2.status_code == 422
