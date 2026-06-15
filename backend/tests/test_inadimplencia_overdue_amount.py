from decimal import Decimal
import pytest

from finacialsim_saas.services.parcela_service import _calculate_overdue_amount


def test_within_carencia_returns_zero_encargos():
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=2,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=3,
    )
    assert result["multa"] == "0.00"
    assert result["juros_acumulado"] == "0.00"
    assert result["valor_corrigido"] == "1000.00"
    assert result["estimativa"] is True


def test_day_1_past_carencia_applies_multa_and_juros():
    """Day 1 past carência: 1 day of juros + multa applied."""
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=1,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=0,
    )
    assert result["multa"] == "20.00"       # 2% of 1000
    assert result["juros_acumulado"] == "0.33"  # 0.033% * 1 day * 1000
    assert result["valor_corrigido"] == "1020.33"


def test_five_days_overdue_no_carencia():
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=5,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=0,
    )
    assert result["multa"] == "20.00"
    assert result["juros_acumulado"] == "1.65"   # 0.033% * 5 * 1000
    assert result["valor_corrigido"] == "1021.65"
    assert result["dias_atraso"] == 5


def test_five_days_overdue_carencia_two():
    """5 days overdue, 2 days grace → 3 dias_com_encargos."""
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=5,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=2,
    )
    assert result["multa"] == "20.00"
    assert result["juros_acumulado"] == "0.99"   # 0.033% * 3 * 1000
    assert result["valor_corrigido"] == "1020.99"


def test_zero_rates_returns_original_value():
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=10,
        multa_pct=Decimal("0.00"),
        juros_diario_pct=Decimal("0.00"),
        carencia_dias=0,
    )
    assert result["multa"] == "0.00"
    assert result["juros_acumulado"] == "0.00"
    assert result["valor_corrigido"] == "1000.00"


# ── Integration tests for get_schedule encargos ──────────────────────────────

import uuid
from datetime import date, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    BusinessRule, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalRenderStatus, ProposalStatus, Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.services.parcela_service import ParcelaService
from finacialsim_saas.settings import get_settings


@pytest_asyncio.fixture
async def overdue_schedule_setup(session: AsyncSession):
    tenant = Tenant(name="OvdSched", slug=f"ovd-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    svc = AuthService(session, get_settings())
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"a-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="A", role=Role.admin,
    )
    client = Client(
        tenant_id=tenant.id, nome="C", cpf_cnpj=f"111.{uuid.uuid4().int % 999:03d}.111-11",
        tipo=ClientType.pf, email=f"c-{uuid.uuid4().hex[:6]}@t.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"S-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("10000"), valor_entrada=Decimal("1000"),
        valor_financiado=Decimal("9000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=1, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("9180"),
        total_pago=Decimal("9180"), total_juros=Decimal("180"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"P-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7,
        snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    overdue_parcela = ParcelaPayment(
        tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=1,
        vencimento=date.today() - timedelta(days=3),
        valor_parcela=Decimal("1000"), status=ParcelaPaymentStatus.overdue,
    )
    session.add(overdue_parcela)
    await session.flush()

    for chave, val in [
        ("inadimplencia_multa_pct",        "2.00"),
        ("inadimplencia_juros_diario_pct", "0.033"),
        ("inadimplencia_carencia_dias",    0),
    ]:
        session.add(BusinessRule(
            id=uuid.uuid4(), tenant_id=tenant.id,
            chave=chave, valor_json=val, descricao="test",
        ))

    await session.commit()

    customer_user = await svc.invite_customer(client.id, RequestContext(
        user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0,
    ))
    await session.commit()

    return {
        "tenant": tenant, "proposal": proposal, "client": client,
        "customer_user": customer_user,
    }


@pytest.mark.asyncio
async def test_get_schedule_includes_encargos_for_overdue(session, overdue_schedule_setup):
    d = overdue_schedule_setup
    ctx = RequestContext(
        user_id=d["customer_user"].id, tenant_id=d["tenant"].id,
        role=Role.customer, iat=0.0, client_id=d["client"].id,
    )
    svc = ParcelaService(session)
    schedule = await svc.get_schedule(d["proposal"].id, ctx)

    overdue_item = next(p for p in schedule["parcelas"] if p["status"] == "overdue")
    assert "encargos" in overdue_item
    enc = overdue_item["encargos"]
    assert enc["multa"] == "20.00"           # 2% of 1000
    assert enc["estimativa"] is True
    assert float(enc["juros_acumulado"]) > 0


@pytest.mark.asyncio
async def test_get_schedule_open_parcela_has_no_encargos(session, overdue_schedule_setup):
    """Future (open) parcelas should not have encargos key."""
    d = overdue_schedule_setup
    ctx = RequestContext(
        user_id=d["customer_user"].id, tenant_id=d["tenant"].id,
        role=Role.customer, iat=0.0, client_id=d["client"].id,
    )

    future_p = ParcelaPayment(
        tenant_id=d["tenant"].id, proposal_id=d["proposal"].id, parcela_num=2,
        vencimento=date.today() + timedelta(days=30),
        valor_parcela=Decimal("1000"), status=ParcelaPaymentStatus.open,
    )
    session.add(future_p)
    await session.commit()

    svc = ParcelaService(session)
    schedule = await svc.get_schedule(d["proposal"].id, ctx)
    open_item = next(p for p in schedule["parcelas"] if p["status"] == "open")
    assert "encargos" not in open_item
