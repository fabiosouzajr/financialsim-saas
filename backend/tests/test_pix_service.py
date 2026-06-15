from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    Client, ClientType, ParcelaPayment, ParcelaPaymentStatus, Proposal,
    ProposalRenderStatus, ProposalStatus, Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.errors import ValidationError
from finacialsim_saas.pix.protocol import PayerInfo, PixChargeData, WebhookEvent
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings

UTC = timezone.utc


def _mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.create_charge.return_value = PixChargeData(
        txid="ignored-by-service",
        brcode="00020126brcode",
        qr_png_bytes=b"PNGDATA",
        amount=Decimal("14000"),
        expires_at=datetime(2026, 10, 31, tzinfo=UTC),
    )
    return provider


def _mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.put.return_value = None
    storage.signed_url.return_value = "https://storage.test/signed"
    return storage


async def _seed_proposal_chain(session, tenant, admin_id, *, client_id, vencimento=None):
    if vencimento is None:
        vencimento = date.today() + timedelta(days=30)
    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=3, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("14000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client_id, vehicle_id=None, criado_por=admin_id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-{uuid.uuid4().hex[:6]}", gerado_por=admin_id,
        validade_dias=7,
        snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    parcela = ParcelaPayment(
        tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=1,
        vencimento=vencimento,
        valor_parcela=Decimal("14000"), status=ParcelaPaymentStatus.open,
    )
    session.add(parcela)
    await session.commit()
    return parcela


@pytest_asyncio.fixture
async def pix_setup(session: AsyncSession):
    """Tenant + admin + client + customer user + confirmed sim + approved proposal +
    open parcela due 2026-09-01 (2026-09-01 + 60 days = 2026-10-31, the deterministic
    BRT-formula assertion target)."""
    tenant = Tenant(name="PixCo", slug=f"pix-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    svc = AuthService(session, get_settings())
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"adm-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )

    client = Client(
        tenant_id=tenant.id, nome="Maria Silva",
        cpf_cnpj="123.456.789-09", tipo=ClientType.pf,
        email=f"maria-{uuid.uuid4().hex[:6]}@example.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    parcela = await _seed_proposal_chain(
        session, tenant, admin.id, client_id=client.id, vencimento=date(2026, 9, 1)
    )

    admin_ctx = RequestContext(user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    customer_user = await svc.invite_customer(client.id, admin_ctx)
    await session.commit()

    return {
        "session": session, "ctx": admin_ctx, "tenant": tenant, "admin_id": admin.id,
        "client": client, "customer_user": customer_user, "parcela": parcela,
    }


@pytest.mark.asyncio
async def test_ensure_charge_builds_payer_info_from_linked_client(pix_setup):
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    await svc._ensure_charge(pix_setup["parcela"])

    _, kwargs = provider.create_charge.call_args
    assert kwargs["payer"] == PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")


@pytest.mark.asyncio
async def test_ensure_charge_threads_due_date_and_validity_days_from_rule(pix_setup):
    """_ensure_charge must pass due_date/validity_days, never expires_in (Cob concept)."""
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    await svc._ensure_charge(pix_setup["parcela"])

    _, kwargs = provider.create_charge.call_args
    assert kwargs["due_date"] == date(2026, 9, 1)
    assert kwargs["validity_days"] == 60   # pix_validade_apos_vencimento_dias default
    assert "expires_in" not in kwargs


@pytest.mark.asyncio
async def test_ensure_charge_blocks_when_proposal_has_no_linked_client(pix_setup):
    """§2b guard — fires before provider.create_charge; applies to fake/efi/cron alike."""
    parcela = await _seed_proposal_chain(
        pix_setup["session"], pix_setup["tenant"], pix_setup["admin_id"], client_id=None
    )
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    with pytest.raises(ValidationError, match="não é possível gerar Pix sem cliente vinculado"):
        await svc._ensure_charge(parcela)

    provider.create_charge.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_charge_reuses_existing_pending_charge_without_calling_provider(pix_setup):
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    first, created_first = await svc._ensure_charge(pix_setup["parcela"])
    second, created_second = await svc._ensure_charge(pix_setup["parcela"])

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    provider.create_charge.assert_called_once()


@pytest.mark.asyncio
async def test_create_charge_for_parcela_sends_pix_link_only_on_fresh_creation(pix_setup):
    """Notification fires on first call (created=True), not on idempotent reuse (created=False).
    This test PASSES against the current code too — it's a regression-pin for the refactor,
    locking in pre-existing behavior so the _ensure_charge extraction can't silently break it."""
    provider = _mock_provider()
    svc = PixService(pix_setup["session"], provider, _mock_storage())

    with patch("finacialsim_saas.notifications.service.NotificationService") as MockNotif:
        mock_enqueue = AsyncMock()
        MockNotif.return_value.enqueue = mock_enqueue

        await svc.create_charge_for_parcela(pix_setup["parcela"].id, pix_setup["ctx"])
        await svc.create_charge_for_parcela(pix_setup["parcela"].id, pix_setup["ctx"])

        assert mock_enqueue.call_count == 1


@pytest.mark.asyncio
async def test_handle_webhook_threads_query_params_to_provider(pix_setup):
    provider = _mock_provider()
    provider.verify_webhook = MagicMock(
        return_value=WebhookEvent(txid="no-such-txid", status="paid", paid_amount=Decimal("10"))
    )
    svc = PixService(pix_setup["session"], provider, _mock_storage())
    headers = {"Content-Type": "application/json"}
    query_params = {"hmac": "shared-secret-token", "ignorar": ""}
    body = b'{"pix": [{"txid": "no-such-txid", "valor": "10.00"}]}'

    await svc.handle_webhook(headers, query_params, body)

    provider.verify_webhook.assert_called_once_with(headers, query_params, body)
