"""Worker render task tests — WeasyPrint is mocked."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finacialsim_saas.data.models import (
    Proposal, ProposalRenderStatus, ProposalStatus,
)
from finacialsim_saas.schemas.proposals import (
    PropostaSnapshot, LojaSnap, VendedorSnap, SimSnap,
)
from finacialsim_saas.workers.tasks import render_proposta_pdf, render_carne_pdf  # noqa: F401


def _make_snap() -> dict:
    return PropostaSnapshot(
        loja=LojaSnap(nome="Loja Teste"),
        vendedor=VendedorSnap(nome="Vendedor"),
        cliente=None,
        veiculo=None,
        sim=SimSnap(
            valor_veiculo="85000.00",
            valor_entrada="17000.00",
            valor_financiado="68000.00",
            prazo_meses=48,
            taxa_mensal="0.012900",
            taxa_anual="0.163000",
            incluir_iof=True,
            iof_total="1224.00",
            tarifas_total="500.00",
            valor_parcela="1987.34",
            total_pago="95392.32",
            total_juros="27392.32",
            cet_mensal="0.013500",
            cet_anual="0.174500",
            extras_acumulado="0.00",
        ),
        extras=[],
        cronograma=[],
    ).model_dump()


def _make_proposal(tenant_id: uuid.UUID) -> MagicMock:
    p = MagicMock(spec=Proposal)
    p.id = uuid.uuid4()
    p.tenant_id = tenant_id
    p.codigo = "PROP-2026-00001"
    p.gerado_em = datetime(2026, 6, 1, tzinfo=timezone.utc)
    p.validade_dias = 7
    p.snapshot_json = _make_snap()
    p.render_status = ProposalRenderStatus.pending
    p.status = ProposalStatus.rascunho
    return p


@pytest.mark.asyncio
async def test_render_proposta_sets_ready():
    tenant_id = uuid.uuid4()
    proposal = _make_proposal(tenant_id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    storage = AsyncMock()
    storage.put = AsyncMock(return_value=f"{tenant_id}/proposals/{proposal.id}/proposta.pdf")

    ctx = {"session_factory": session_factory, "storage_backend": storage}

    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 fake"
        await render_proposta_pdf(ctx, str(proposal.id))

    assert proposal.render_status == ProposalRenderStatus.ready
    assert proposal.status == ProposalStatus.pronta
    assert proposal.pdf_key is not None
    storage.put.assert_called_once()


@pytest.mark.asyncio
async def test_render_proposta_sets_failed_on_exception():
    tenant_id = uuid.uuid4()
    proposal = _make_proposal(tenant_id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    ctx = {"session_factory": session_factory, "storage_backend": AsyncMock()}

    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.side_effect = RuntimeError("render boom")
        await render_proposta_pdf(ctx, str(proposal.id))

    assert proposal.render_status == ProposalRenderStatus.failed
    assert proposal.render_error is not None
    assert "render boom" in proposal.render_error


@pytest.mark.asyncio
async def test_render_proposta_not_found_is_silent():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    ctx = {"session_factory": session_factory, "storage_backend": AsyncMock()}
    await render_proposta_pdf(ctx, str(uuid.uuid4()))


def _make_snap_with_logo() -> dict:
    return PropostaSnapshot(
        loja=LojaSnap(nome="Loja Teste", logo_key="tenant-abc/logo/logo.png"),
        vendedor=VendedorSnap(nome="Vendedor"),
        cliente=None,
        veiculo=None,
        sim=SimSnap(
            valor_veiculo="85000.00",
            valor_entrada="17000.00",
            valor_financiado="68000.00",
            prazo_meses=48,
            taxa_mensal="0.012900",
            taxa_anual="0.163000",
            incluir_iof=True,
            iof_total="1224.00",
            tarifas_total="500.00",
            valor_parcela="1987.34",
            total_pago="95392.32",
            total_juros="27392.32",
            cet_mensal="0.013500",
            cet_anual="0.174500",
            extras_acumulado="0.00",
        ),
        extras=[],
        cronograma=[],
    ).model_dump()


def _make_proposal_with_logo(tenant_id: uuid.UUID) -> MagicMock:
    p = MagicMock(spec=Proposal)
    p.id = uuid.uuid4()
    p.tenant_id = tenant_id
    p.codigo = "PROP-2026-00002"
    p.gerado_em = datetime(2026, 6, 1, tzinfo=timezone.utc)
    p.validade_dias = 7
    p.snapshot_json = _make_snap_with_logo()
    p.render_status = ProposalRenderStatus.pending
    p.status = ProposalStatus.rascunho
    return p


@pytest.fixture()
def proposal_with_logo():
    tenant_id = uuid.uuid4()
    proposal = _make_proposal_with_logo(tenant_id)
    session = AsyncMock()
    session.get = AsyncMock(return_value=proposal)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    storage = AsyncMock()
    storage.put = AsyncMock(return_value=None)
    return proposal, session_factory, storage


@pytest.mark.asyncio
async def test_render_proposta_embeds_logo(proposal_with_logo):
    """render_proposta_pdf embeds logo as base64 data URI when logo_key is set."""
    proposal, session_factory, storage = proposal_with_logo
    storage.get = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")  # minimal PNG header

    fake_pdf = b"%PDF-1.4 fake"
    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.return_value = fake_pdf
        await render_proposta_pdf(
            {"session_factory": session_factory, "storage_backend": storage},
            str(proposal.id),
        )

    # HTML() was called with a string containing data:image/png;base64
    html_arg = mock_html.call_args[1]["string"]
    assert "data:image/png;base64" in html_arg


@pytest.mark.asyncio
async def test_render_proposta_continues_without_logo_on_storage_error(proposal_with_logo):
    """render_proposta_pdf succeeds even when logo storage.get() raises."""
    proposal, session_factory, storage = proposal_with_logo
    storage.get = AsyncMock(side_effect=Exception("S3 error"))

    fake_pdf = b"%PDF-1.4 fake"
    with patch("finacialsim_saas.workers.tasks.HTML") as mock_html:
        mock_html.return_value.write_pdf.return_value = fake_pdf
        await render_proposta_pdf(
            {"session_factory": session_factory, "storage_backend": storage},
            str(proposal.id),
        )

    # PDF was still produced despite storage error — write_pdf was called
    mock_html.return_value.write_pdf.assert_called_once()
