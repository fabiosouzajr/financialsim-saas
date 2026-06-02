"""Integration tests for ProposalService against a real Postgres."""
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import (
    AmortizationRow, NotificationsOutbox, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalRenderStatus, ProposalStatus, Role, Simulation,
    SimulationStatus, Tenant,
)
from finacialsim_saas.errors import ConflictError, ValidationError
from finacialsim_saas.services.proposal_service import ProposalService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.local import LocalVolumeBackend


@pytest.fixture
async def ctx_and_session(engine):
    factory = build_session_factory(engine)
    async with factory() as s:
        # Create tenant
        t = Tenant(name="Loja Teste", slug=f"loja-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        # Create user via AuthService
        svc = AuthService(s, get_settings())
        email = f"v-{uuid.uuid4().hex[:8]}@test.com"
        user = await svc.register_user(
            tenant_id=t.id,
            email=email,
            name="Vendedor",
            password="pw123",
            role=Role.user,
        )
        await s.commit()
        await s.refresh(user)
        ctx = RequestContext(
            user_id=user.id, tenant_id=t.id, role=Role.user, iat=0.0
        )
        yield ctx, s


async def _seed_simulation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    client_id: uuid.UUID | None = None,
) -> Simulation:
    sim = Simulation(
        tenant_id=tenant_id,
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
        criado_por=user_id,
        client_id=client_id,
    )
    session.add(sim)
    await session.flush()
    for i in range(1, 4):
        session.add(AmortizationRow(
            simulation_id=sim.id,
            tenant_id=tenant_id,
            numero_parcela=i,
            data_vencimento=date(2026, 6 + i, 1),
            dias_periodo=30,
            saldo_anterior=Decimal("68000.00") - (i - 1) * Decimal("1110.14"),
            juros=Decimal("877.20"),
            amortizacao=Decimal("1110.14"),
            parcela=Decimal("1987.34"),
            saldo_devedor=Decimal("68000.00") - i * Decimal("1110.14"),
            extras_total=Decimal("0.00"),
            parcela_total=Decimal("1987.34"),
            ajuste_arredondamento=Decimal("0.00"),
        ))
    await session.commit()
    await session.refresh(sim)
    return sim


def _make_svc(session, tmp_path: Path) -> ProposalService:
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")
    return ProposalService(session, arq, storage)


@pytest.mark.asyncio
async def test_create_proposal_returns_pending(ctx_and_session, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    svc = _make_svc(session, tmp_path)
    proposal = await svc.create(sim.id, ctx)
    assert proposal.render_status == ProposalRenderStatus.pending
    assert proposal.status == ProposalStatus.rascunho
    assert proposal.codigo.startswith("PROP-2026-")
    svc._arq.enqueue_job.assert_called_once_with("render_proposta_pdf", str(proposal.id))


@pytest.mark.asyncio
async def test_create_proposal_duplicate_raises_409(ctx_and_session, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    svc = _make_svc(session, tmp_path)
    await svc.create(sim.id, ctx)
    with pytest.raises(ConflictError):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_create_proposal_rascunho_sim_raises(ctx_and_session, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    sim.status = SimulationStatus.rascunho
    await session.commit()
    svc = _make_svc(session, tmp_path)
    with pytest.raises(ValidationError):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_approve_generates_parcela_payments(ctx_and_session, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    svc = _make_svc(session, tmp_path)
    proposal = await svc.create(sim.id, ctx)
    # Simulate worker completing the render
    proposal.render_status = ProposalRenderStatus.ready
    proposal.status = ProposalStatus.ready
    await session.commit()
    await svc.approve(proposal.id, ctx)
    payments = list(await session.scalars(
        select(ParcelaPayment).where(ParcelaPayment.proposal_id == proposal.id)
    ))
    assert len(payments) == 3
    assert all(p.status == ParcelaPaymentStatus.open for p in payments)


@pytest.mark.asyncio
async def test_approve_writes_customer_invite_outbox(ctx_and_session, tmp_path):
    """approve() writes customer_invite outbox when auth_service is injected and sim has client_id."""
    from finacialsim_saas.data.models import Client, ClientType
    ctx, session = ctx_and_session
    # Create a client linked to the simulation
    client = Client(
        tenant_id=ctx.tenant_id,
        nome="Cliente Teste",
        cpf_cnpj=f"000.{uuid.uuid4().int % 999:03d}.000-00",
        tipo=ClientType.pf,
        email=f"cli-{uuid.uuid4().hex[:6]}@example.com",
        criado_por=ctx.user_id,
    )
    session.add(client)
    await session.flush()
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id, client_id=client.id)
    auth_svc = AuthService(session, get_settings())
    arq = AsyncMock()
    storage = LocalVolumeBackend(root=tmp_path, secret="s", base_url="http://localhost:8000")
    svc = ProposalService(session, arq, storage, auth_service=auth_svc)
    proposal = await svc.create(sim.id, ctx)
    proposal.render_status = ProposalRenderStatus.ready
    proposal.status = ProposalStatus.ready
    await session.commit()
    await svc.approve(proposal.id, ctx)
    outbox = list(await session.scalars(
        select(NotificationsOutbox)
        .where(NotificationsOutbox.tenant_id == ctx.tenant_id)
        .where(NotificationsOutbox.template_key == "customer_invite")
    ))
    assert len(outbox) == 1
    assert outbox[0].payload_json["proposal_id"] == str(proposal.id)


@pytest.mark.asyncio
async def test_cancel_cascades_parcela_payments(ctx_and_session, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    svc = _make_svc(session, tmp_path)
    proposal = await svc.create(sim.id, ctx)
    proposal.render_status = ProposalRenderStatus.ready
    proposal.status = ProposalStatus.ready
    await session.commit()
    await svc.approve(proposal.id, ctx)
    await svc.cancel(proposal.id, ctx)
    payments = list(await session.scalars(
        select(ParcelaPayment).where(ParcelaPayment.proposal_id == proposal.id)
    ))
    assert all(p.status == ParcelaPaymentStatus.canceled for p in payments)
    assert proposal.status == ProposalStatus.cancelada


@pytest.mark.asyncio
async def test_create_carne_rejects_non_aprovada(ctx_and_session, tmp_path):
    ctx, session = ctx_and_session
    sim = await _seed_simulation(session, ctx.tenant_id, ctx.user_id)
    svc = _make_svc(session, tmp_path)
    proposal = await svc.create(sim.id, ctx)
    with pytest.raises(ValidationError, match="approved"):
        await svc.create_carne(proposal.id, ctx)
