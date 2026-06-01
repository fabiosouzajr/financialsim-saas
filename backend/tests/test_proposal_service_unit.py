"""Unit tests for ProposalService using mocked session + arq."""
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    Proposal, Role, Simulation, SimulationStatus,
)
from finacialsim_saas.errors import ConflictError, NotFoundError, ValidationError
from finacialsim_saas.services.proposal_service import ProposalService


def _ctx(role: Role = Role.user) -> RequestContext:
    return RequestContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role=role,
        iat=0.0,
    )


def _make_sim(tenant_id: uuid.UUID, status=SimulationStatus.confirmado) -> MagicMock:
    s = MagicMock(spec=Simulation)
    s.id = uuid.uuid4()
    s.tenant_id = tenant_id
    s.client_id = None
    s.vehicle_id = None
    s.status = status
    s.valor_veiculo = Decimal("85000.00")
    s.valor_entrada = Decimal("17000.00")
    s.valor_financiado = Decimal("68000.00")
    s.taxa_mensal = Decimal("0.012900")
    s.prazo_meses = 48
    s.data_liberacao = date(2026, 6, 1)
    s.primeiro_vencimento = date(2026, 7, 1)
    s.incluir_iof = True
    s.iof_total = Decimal("1224.00")
    s.parcela_financiamento = Decimal("1987.34")
    s.total_pago = Decimal("95392.32")
    s.total_juros = Decimal("27392.32")
    s.cet_mensal = Decimal("0.013500")
    s.cet_anual = Decimal("0.174500")
    return s


@pytest.mark.asyncio
async def test_create_rejects_wrong_tenant():
    ctx = _ctx()
    sim = _make_sim(tenant_id=uuid.uuid4())  # different tenant
    session = AsyncMock()
    session.get = AsyncMock(return_value=sim)
    arq = AsyncMock()
    storage = AsyncMock()
    svc = ProposalService(session, arq, storage)
    with pytest.raises(NotFoundError):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_create_rejects_non_confirmado():
    ctx = _ctx()
    sim = _make_sim(tenant_id=ctx.tenant_id, status=SimulationStatus.rascunho)
    session = AsyncMock()
    session.get = AsyncMock(return_value=sim)
    arq = AsyncMock()
    storage = AsyncMock()
    svc = ProposalService(session, arq, storage)
    with pytest.raises(ValidationError, match="confirmado"):
        await svc.create(sim.id, ctx)


@pytest.mark.asyncio
async def test_get_cross_tenant_raises():
    ctx = _ctx()
    proposal = MagicMock(spec=Proposal)
    proposal.tenant_id = uuid.uuid4()  # different tenant
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    arq = AsyncMock()
    storage = AsyncMock()
    svc = ProposalService(session, arq, storage)
    with pytest.raises(NotFoundError):
        await svc.get(proposal.id, ctx)
