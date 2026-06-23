"""Tests for Phase 6 ProposalService changes: invite on approve, cancel with cleanup."""
import uuid
import pytest
from unittest.mock import AsyncMock
from sqlalchemy import select

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Role, ParcelaPaymentStatus, User


@pytest.mark.asyncio
async def test_approve_calls_invite_customer(session, engine):
    """approve() creates customer user after creating parcelas."""
    from finacialsim_saas.services.proposal_service import ProposalService
    from finacialsim_saas.data.models import (
        Tenant, Client, ClientType, Simulation, SimulationStatus,
        Proposal, ProposalStatus, ProposalRenderStatus,
    )
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    from finacialsim_saas.storage.local import LocalVolumeBackend
    from decimal import Decimal
    from datetime import date
    from pathlib import Path
    import tempfile

    tenant = Tenant(name="Phase6Co", slug=f"ph6-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    auth_svc = AuthService(session, get_settings())
    admin = await auth_svc.register_user(
        tenant_id=tenant.id, email=f"adm-ph6-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )

    client = Client(
        tenant_id=tenant.id, nome="Test Client",
        cpf_cnpj=f"999.888.{uuid.uuid4().int % 999:03d}-77",
        tipo=ClientType.pf, email=f"testclient-{uuid.uuid4().hex[:6]}@example.com",
        criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    snap_json = {
        "sim": {
            "valor_veiculo": "50000", "valor_financiado": "40000",
            "valor_entrada": "10000", "prazo_meses": 2,
            "taxa_mensal": "0.02", "taxa_anual": "0.27",
            "incluir_iof": False, "iof_total": "0", "tarifas_total": "0",
            "valor_parcela": "21000", "total_pago": "42000",
            "total_juros": "2000", "cet_mensal": "0.021", "cet_anual": "0.28",
            "extras_acumulado": "0",
        },
        "cronograma": [
            {"numero": 1, "venc": date.today().isoformat(), "parcela_total": "21000",
             "juros": "800", "amortizacao": "20200", "parcela": "21000",
             "extras": "0", "saldo": "19800"},
            {"numero": 2, "venc": date.today().isoformat(), "parcela_total": "21000",
             "juros": "396", "amortizacao": "20604", "parcela": "21000",
             "extras": "0", "saldo": "0"},
        ],
        "loja": {"nome": "T", "cnpj": "00.000.000/0001-00", "endereco": "", "telefone": ""},
        "vendedor": {"nome": "A"},
        "extras": [],
        "cliente": None, "veiculo": None,
    }

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-PH6-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=2, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("21000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-PH6-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7, snapshot_json=snap_json,
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.pronta,
    )
    session.add(proposal)
    await session.commit()

    ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalVolumeBackend(root=Path(tmpdir), secret="s", base_url="http://test")
        arq_mock = AsyncMock()
        svc = ProposalService(session=session, arq=arq_mock, storage=storage, auth_service=auth_svc)

        result = await svc.approve(proposal.id, ctx)

    assert result.status == ProposalStatus.aprovada

    customer = await session.scalar(
        select(User).where(
            User.client_id == client.id,
            User.role == Role.customer,
            User.tenant_id == tenant.id,
        )
    )
    assert customer is not None
