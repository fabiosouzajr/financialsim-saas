from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timezone

import httpx
from loguru import logger
from sqlalchemy import delete, select

from finacialsim_saas.data.models import ProviderHealth
from finacialsim_saas.services.indicators_service import IndicatorsService

UTC = timezone.utc

BACEN_CODIGOS = ["SELIC", "CDI", "IPCA", "TX_BACEN_VEIC"]
PROVIDER_PING_URLS = {
    "fipe_parallelum": "https://parallelum.com.br/fipe/api/v1/carros/marcas",
    "fipe_brasilapi": "https://brasilapi.com.br/api/fipe/marcas/v1/carros",
    "bacen_sgs": (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
    ),
    "bacen_brasilapi": "https://brasilapi.com.br/api/taxas/v1/Selic",
}


async def ping(ctx: dict) -> str:
    """Health-check job. Enqueue it to verify the worker is alive and Redis is reachable."""
    logger.info("ping job executed")
    return "pong"


async def update_bacen_indicators(ctx: dict) -> None:
    today = date.today()
    lock_key = f"lock:update_bacen_indicators:{today.isoformat()}"
    redis = ctx["redis"]
    acquired = await redis.set(lock_key, "1", nx=True, ex=86400)
    if not acquired:
        logger.info("update_bacen_indicators: already ran today, skipping")
        return

    chain = ctx["bacen_chain"]
    session_factory = ctx["session_factory"]
    from datetime import timedelta
    one_year_ago = today - timedelta(days=366)

    async with session_factory() as session:
        svc = IndicatorsService(session)
        for codigo in BACEN_CODIGOS:
            result = await chain.fetch({
                "codigo": codigo,
                "data_inicial": one_year_ago,
                "data_final": today,
            })
            if result.is_ok:
                for point in result.value:
                    await svc.upsert(point)
                await session.commit()
                logger.info(f"update_bacen_indicators: {codigo} ok ({len(result.value)} pts)")
            else:
                logger.warning(f"update_bacen_indicators: {codigo} failed: {result.error}")


async def prune_fipe_cache(ctx: dict) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        now = datetime.now(UTC)
        from sqlalchemy import text
        await session.execute(
            text(
                "DELETE FROM fipe_cache "
                "WHERE coletado_em + ttl_horas * interval '1 hour' < :now"
            ),
            {"now": now},
        )
        await session.commit()
    logger.info("prune_fipe_cache: complete")


async def verify_provider_health(ctx: dict) -> None:
    http: httpx.AsyncClient = ctx["http_client"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        for provider_name, url in PROVIDER_PING_URLS.items():
            start = time.monotonic()
            try:
                resp = await http.get(url, timeout=10.0)
                latency_ms = int((time.monotonic() - start) * 1000)
                success = resp.status_code < 400
                error = None if success else f"HTTP {resp.status_code}"
            except Exception as exc:
                latency_ms = None
                success = False
                error = str(exc)[:200]

            session.add(
                ProviderHealth(
                    provider_name=provider_name,
                    latency_ms=latency_ms,
                    success=success,
                    error=error,
                )
            )
            await session.flush()

            keep_ids = (
                await session.scalars(
                    select(ProviderHealth.id)
                    .where(ProviderHealth.provider_name == provider_name)
                    .order_by(ProviderHealth.checked_at.desc())
                    .limit(50)
                )
            ).all()
            await session.execute(
                delete(ProviderHealth).where(
                    ProviderHealth.provider_name == provider_name,
                    ~ProviderHealth.id.in_(keep_ids),
                )
            )

        await session.commit()
    logger.info("verify_provider_health: complete")


# ── PDF render tasks ──────────────────────────────────────────────────────────

import uuid as _uuid  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from jinja2 import Environment as _Env, FileSystemLoader as _FSL  # noqa: E402
from weasyprint import CSS, HTML  # type: ignore[import-untyped]  # noqa: E402

from finacialsim_saas.data.models import (  # noqa: E402
    Proposal as _Proposal,
    ProposalRenderStatus as _PRS,
    ProposalStatus as _PS,
)
from finacialsim_saas.schemas.proposals import PropostaSnapshot as _Snap  # noqa: E402
from finacialsim_saas.storage import StorageBackend as _SB  # noqa: E402
from finacialsim_saas.utils.br_format import (  # noqa: E402
    format_brl as _fbrl,
    format_date_br as _fdate,
    format_pct as _fpct,
    format_cpf_cnpj as _fcpf,
)

_REPORTS = _Path(__file__).resolve().parents[1] / "reports"
_jinja = _Env(loader=_FSL(str(_REPORTS)), autoescape=True)

_MODALIDADE_LABEL = {
    "mensal_continuo": "Mensal contínuo",
    "rateio_meses": "Rateio em meses",
    "unico_inicial": "Único (1ª parcela)",
}


def _proposta_ctx(snap: _Snap, proposal: _Proposal) -> dict:
    from datetime import date as _date
    from decimal import Decimal

    def _d(s: object) -> Decimal:
        return Decimal(str(s))

    s = snap.sim
    rows = snap.cronograma
    n = len(rows)
    pt1 = _d(rows[0].parcela_total) if rows else Decimal("0")
    pta = _d(rows[min(11, n - 1)].parcela_total) if rows else Decimal("0")
    pct_e = _d(s.valor_entrada) / _d(s.valor_veiculo) if _d(s.valor_veiculo) else Decimal("0")
    pct_j = _d(s.total_juros) / _d(s.valor_financiado) if _d(s.valor_financiado) else Decimal("0")
    total_cliente = _d(s.total_pago) + _d(s.extras_acumulado)

    return {
        "loja": snap.loja.model_dump(),
        "vendedor": snap.vendedor.model_dump(),
        "proposal": {
            "codigo": proposal.codigo,
            "gerado_em_br": _fdate(proposal.gerado_em.date()),
            "validade_dias": proposal.validade_dias,
        },
        "cliente": {
            "nome": snap.cliente.nome if snap.cliente else "",
            "tipo": snap.cliente.tipo if snap.cliente else "PF",
            "cpf_cnpj_fmt": _fcpf(snap.cliente.cpf_cnpj, snap.cliente.tipo) if snap.cliente else "",
            "telefone": snap.cliente.telefone if snap.cliente else None,
        },
        "veiculo": {
            "marca": snap.veiculo.marca if snap.veiculo else "",
            "modelo": snap.veiculo.modelo if snap.veiculo else "",
            "ano_modelo": snap.veiculo.ano_modelo if snap.veiculo else 0,
            "codigo_fipe": snap.veiculo.codigo_fipe if snap.veiculo else None,
            "mes_referencia_fipe": snap.veiculo.mes_referencia_fipe if snap.veiculo else None,
        },
        "sim": {
            "valor_veiculo_brl": _fbrl(_d(s.valor_veiculo)),
            "valor_financiado_brl": _fbrl(_d(s.valor_financiado)),
            "valor_entrada_brl": _fbrl(_d(s.valor_entrada)),
            "pct_entrada_pct": _fpct(pct_e),
            "prazo_meses": s.prazo_meses,
            "taxa_juros_mes_pct": _fpct(_d(s.taxa_mensal), 4),
            "taxa_juros_ano_pct": _fpct(_d(s.taxa_anual), 2),
            "cet_mes_pct": _fpct(_d(s.cet_mensal), 4),
            "cet_ano_pct": _fpct(_d(s.cet_anual), 2),
            "incluir_iof": s.incluir_iof,
            "iof_total_brl": _fbrl(_d(s.iof_total)),
            "tarifas_total_brl": _fbrl(_d(s.tarifas_total)),
            "valor_parcela_brl": _fbrl(_d(s.valor_parcela)),
            "parcela_total_1ano_brl": _fbrl(pt1),
            "parcela_total_apos_brl": _fbrl(pta),
            "total_pago_brl": _fbrl(_d(s.total_pago)),
            "total_juros_brl": _fbrl(_d(s.total_juros)),
            "pct_juros_pct": _fpct(pct_j),
            "total_pago_cliente_brl": _fbrl(total_cliente),
        },
        "extras": [
            {
                "nome": e.nome,
                "modalidade_label": _MODALIDADE_LABEL.get(e.modalidade, e.modalidade),
                "valor_total_brl": _fbrl(_d(e.valor_total)),
                "duracao_meses": e.duracao_meses,
                "valor_por_parcela_brl": _fbrl(_d(e.valor_por_parcela)),
            }
            for e in snap.extras
        ],
        "cronograma": [
            {
                "numero": r.numero,
                "venc": _fdate(_date.fromisoformat(r.venc)),
                "juros_brl": _fbrl(_d(r.juros)),
                "amortizacao_brl": _fbrl(_d(r.amortizacao)),
                "parcela_brl": _fbrl(_d(r.parcela)),
                "extras_brl": _fbrl(_d(r.extras)),
                "parcela_total_brl": _fbrl(_d(r.parcela_total)),
                "saldo_brl": _fbrl(_d(r.saldo)),
            }
            for r in snap.cronograma
        ],
    }


def _carne_ctx(snap: _Snap, proposal: _Proposal) -> dict:
    from datetime import date as _date
    from decimal import Decimal

    def _d(s: object) -> Decimal:
        return Decimal(str(s))

    total = len(snap.cronograma)
    return {
        "loja": snap.loja.model_dump(),
        "proposal": {"codigo": proposal.codigo},
        "cliente": {
            "nome": snap.cliente.nome if snap.cliente else "",
            "cpf_cnpj_fmt": _fcpf(snap.cliente.cpf_cnpj, snap.cliente.tipo)
            if snap.cliente else "",
        },
        "veiculo": {
            "descricao": snap.veiculo.descricao if snap.veiculo else "",
            "placa": snap.veiculo.placa if snap.veiculo else None,
        },
        "parcelas": [
            {
                "numero": r.numero,
                "total": total,
                "vencimento_br": _fdate(_date.fromisoformat(r.venc)),
                "valor_total_brl": _fbrl(_d(r.parcela_total)),
            }
            for r in snap.cronograma
        ],
    }


async def render_proposta_pdf(ctx: dict, proposal_id: str) -> None:
    session_factory = ctx["session_factory"]
    storage: _SB = ctx["storage_backend"]

    async with session_factory() as session:
        proposal = await session.get(_Proposal, _uuid.UUID(proposal_id))
        if proposal is None:
            logger.error(f"render_proposta_pdf: proposal {proposal_id} not found")
            return

        proposal.render_status = _PRS.rendering
        await session.commit()

        try:
            snap = _Snap.model_validate(proposal.snapshot_json)
            html_str = _jinja.get_template("proposta.html").render(**_proposta_ctx(snap, proposal))
            css_path = _REPORTS / "proposta.css"
            stylesheets = [CSS(filename=str(css_path))] if css_path.exists() else []
            pdf = await asyncio.to_thread(HTML(string=html_str).write_pdf, stylesheets=stylesheets)

            key = f"{proposal.tenant_id}/proposals/{proposal.id}/proposta.pdf"
            await storage.put(key, pdf, "application/pdf")

            proposal.pdf_key = key
            proposal.render_status = _PRS.ready
            proposal.status = _PS.ready
            await session.commit()
            logger.info(f"render_proposta_pdf: {proposal_id} → {len(pdf):,} bytes")

        except Exception as exc:
            logger.exception(f"render_proposta_pdf: {proposal_id} failed")
            proposal.render_status = _PRS.failed
            proposal.render_error = str(exc)[:1000]
            await session.commit()


async def render_carne_pdf(ctx: dict, proposal_id: str) -> None:
    session_factory = ctx["session_factory"]
    storage: _SB = ctx["storage_backend"]

    async with session_factory() as session:
        proposal = await session.get(_Proposal, _uuid.UUID(proposal_id))
        if proposal is None:
            return

        try:
            snap = _Snap.model_validate(proposal.snapshot_json)
            html_str = _jinja.get_template("carne.html").render(**_carne_ctx(snap, proposal))
            css_path = _REPORTS / "carne.css"
            stylesheets = [CSS(filename=str(css_path))] if css_path.exists() else []
            pdf = await asyncio.to_thread(HTML(string=html_str).write_pdf, stylesheets=stylesheets)

            key = f"{proposal.tenant_id}/proposals/{proposal.id}/carne.pdf"
            await storage.put(key, pdf, "application/pdf")

            proposal.carne_key = key
            await session.commit()
            logger.info(f"render_carne_pdf: {proposal_id} → {len(pdf):,} bytes")

        except Exception as exc:
            logger.exception(f"render_carne_pdf: {proposal_id} failed")
            proposal.render_error = f"carne: {str(exc)[:990]}"
            await session.commit()
