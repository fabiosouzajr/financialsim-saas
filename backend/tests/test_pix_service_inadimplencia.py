"""Integration tests for _ensure_charge overdue regeneration logic."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    BusinessRule, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus,
    PixCharge, PixChargeStatus, Proposal, ProposalRenderStatus, ProposalStatus,
    Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings

UTC = timezone.utc


@pytest_asyncio.fixture
async def inad_setup(session: AsyncSession):
    """Tenant with multa 2%, juros 0.033%/day, carencia 0. Overdue parcela."""
    tenant = Tenant(name="InadSvc", slug=f"inad-svc-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    svc_auth = AuthService(session, get_settings())
    admin = await svc_auth.register_user(
        tenant_id=tenant.id, email=f"adm-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )
    client = Client(
        tenant_id=tenant.id, nome="Bob", cpf_cnpj=f"000.{uuid.uuid4().int % 999:03d}.000-00",
        tipo=ClientType.pf, email=f"bob-{uuid.uuid4().hex[:6]}@example.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=1, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("42000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7,
        snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    parcela = ParcelaPayment(
        tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=1,
        vencimento=date.today() - timedelta(days=5),
        valor_parcela=Decimal("1000"), status=ParcelaPaymentStatus.overdue,
    )
    session.add(parcela)
    await session.flush()

    # Configure penalty rules
    for chave, valor in [
        ("inadimplencia_multa_pct",        "2.00"),
        ("inadimplencia_juros_diario_pct", "0.033"),
        ("inadimplencia_carencia_dias",    0),
    ]:
        session.add(BusinessRule(
            id=uuid.uuid4(), tenant_id=tenant.id,
            chave=chave, valor_json=valor, descricao="test",
        ))

    await session.commit()

    ctx = RequestContext(
        user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0,
    )
    storage = AsyncMock()
    storage.put = AsyncMock(return_value="pix/test/qr.png")
    storage.signed_url = AsyncMock(return_value="https://fake.url/qr.png")
    provider = InMemoryFakePixProvider()
    return {
        "tenant": tenant, "parcela": parcela, "ctx": ctx,
        "storage": storage, "provider": provider, "session": session,
    }


@pytest.mark.asyncio
async def test_stale_overdue_charge_is_regenerated(session: AsyncSession, inad_setup):
    """An overdue charge created yesterday is canceled and a new one created."""
    parcela = inad_setup["parcela"]
    storage = inad_setup["storage"]
    provider = inad_setup["provider"]
    ctx = inad_setup["ctx"]

    pix_svc = PixService(session, provider, storage)

    # First call: creates a charge
    charge1, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    assert charge1.status == PixChargeStatus.pending

    # Wind back criado_em to yesterday so it's stale
    charge1.criado_em = datetime(2020, 1, 1, tzinfo=UTC)
    await session.commit()

    # Second call: stale → regenerate
    charge2, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)

    await session.refresh(charge1)
    assert charge1.status == PixChargeStatus.canceled
    assert charge2.id != charge1.id
    assert charge2.status == PixChargeStatus.pending


@pytest.mark.asyncio
async def test_fresh_overdue_charge_not_regenerated(session: AsyncSession, inad_setup):
    """An overdue charge created today is returned as-is (no regeneration)."""
    parcela = inad_setup["parcela"]
    storage = inad_setup["storage"]
    provider = inad_setup["provider"]
    ctx = inad_setup["ctx"]

    pix_svc = PixService(session, provider, storage)

    charge1, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    charge2, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)

    assert charge1.id == charge2.id  # same charge, not regenerated


@pytest.mark.asyncio
async def test_overdue_within_carencia_not_regenerated(session: AsyncSession, inad_setup):
    """Within grace period, stale overdue charge is NOT regenerated."""
    parcela = inad_setup["parcela"]
    session_obj = inad_setup["session"]
    storage = inad_setup["storage"]
    provider = inad_setup["provider"]
    ctx = inad_setup["ctx"]
    tenant = inad_setup["tenant"]

    # Set carencia_dias = 10 (parcela is 5 days overdue, so within grace)
    from sqlalchemy import select as sa_select
    carencia_rule = await session_obj.scalar(
        sa_select(BusinessRule).where(
            BusinessRule.tenant_id == tenant.id,
            BusinessRule.chave == "inadimplencia_carencia_dias",
        )
    )
    carencia_rule.valor_json = 10
    await session_obj.commit()

    pix_svc = PixService(session, provider, storage)

    charge1, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    charge1.criado_em = datetime(2020, 1, 1, tzinfo=UTC)
    await session.commit()

    charge2, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    assert charge1.id == charge2.id  # NOT regenerated — within carência
