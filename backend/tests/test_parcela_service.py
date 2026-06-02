import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    Role, Tenant, User, Client, ClientType, Simulation, SimulationStatus,
    Proposal, ProposalStatus, ProposalRenderStatus, ParcelaPayment,
    ParcelaPaymentStatus, AuditLog, NotificationsOutbox,
)
from finacialsim_saas.services.parcela_service import ParcelaService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.errors import NotFoundError


@pytest_asyncio.fixture
async def setup(session: AsyncSession):
    """Tenant + admin + client + customer + approved proposal + parcelas."""
    tenant = Tenant(name="ParcelaCo", slug=f"parcela-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, get_settings())
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"adm-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )

    client = Client(
        tenant_id=tenant.id, nome="Ana", cpf_cnpj=f"123.{uuid.uuid4().int % 999:03d}.456-78",
        tipo=ClientType.pf, email=f"ana-{uuid.uuid4().hex[:6]}@example.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=3, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("14000"),
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
        validade_dias=7, snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    today = date.today()
    for i in range(1, 4):
        p = ParcelaPayment(
            tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=i,
            vencimento=today + timedelta(days=30 * i),
            valor_parcela=Decimal("14000"), status=ParcelaPaymentStatus.open,
        )
        session.add(p)
    await session.commit()

    admin_ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    customer_user = await svc.invite_customer(client.id, admin_ctx)
    customer_user.password_hash = svc._hash_pw("cpass")
    await session.commit()

    return {
        "tenant": tenant, "admin": admin, "client": client,
        "sim": sim, "proposal": proposal, "customer_user": customer_user,
    }


@pytest.mark.asyncio
async def test_list_for_customer_returns_proposals(session, setup):
    cu = setup["customer_user"]
    ctx = RequestContext(
        user_id=cu.id, tenant_id=setup["tenant"].id,
        role=Role.customer, iat=0.0, client_id=setup["client"].id,
    )
    svc = ParcelaService(session)
    items = await svc.list_for_customer(ctx)
    assert len(items) == 1
    item = items[0]
    assert item["proposal_id"] == str(setup["proposal"].id)
    assert item["status_counts"]["open"] == 3


@pytest.mark.asyncio
async def test_get_schedule_returns_parcelas(session, setup):
    cu = setup["customer_user"]
    ctx = RequestContext(
        user_id=cu.id, tenant_id=setup["tenant"].id,
        role=Role.customer, iat=0.0, client_id=setup["client"].id,
    )
    svc = ParcelaService(session)
    schedule = await svc.get_schedule(setup["proposal"].id, ctx)
    assert len(schedule["parcelas"]) == 3
    assert schedule["next_open_parcela_id"] is not None


@pytest.mark.asyncio
async def test_cannot_access_other_customer_proposal(session, setup):
    other_client_id = uuid.uuid4()
    ctx = RequestContext(
        user_id=uuid.uuid4(), tenant_id=setup["tenant"].id,
        role=Role.customer, iat=0.0, client_id=other_client_id,
    )
    svc = ParcelaService(session)
    with pytest.raises(NotFoundError):
        await svc.get_schedule(setup["proposal"].id, ctx)


@pytest.mark.asyncio
async def test_mark_overdue_flips_past_due_parcelas(session, setup):
    past_date = date.today() - timedelta(days=5)
    overdue_p = ParcelaPayment(
        tenant_id=setup["tenant"].id, proposal_id=setup["proposal"].id,
        parcela_num=99, vencimento=past_date,
        valor_parcela=Decimal("100"), status=ParcelaPaymentStatus.open,
    )
    session.add(overdue_p)
    await session.commit()

    svc = ParcelaService(session)
    await svc.mark_overdue()

    await session.refresh(overdue_p)
    assert overdue_p.status == ParcelaPaymentStatus.overdue

    audit = await session.scalar(
        select(AuditLog).where(
            AuditLog.entidade == "parcela_payments",
            AuditLog.entidade_id == overdue_p.id,
            AuditLog.acao == "parcela_overdue",
        )
    )
    assert audit is not None

    outbox = await session.scalar(
        select(NotificationsOutbox).where(
            NotificationsOutbox.type == "parcela_overdue",
            NotificationsOutbox.tenant_id == setup["tenant"].id,
        )
    )
    assert outbox is not None
    assert outbox.payload["parcela_id"] == str(overdue_p.id)
