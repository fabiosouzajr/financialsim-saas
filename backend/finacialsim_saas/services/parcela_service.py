from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalStatus, Role, Simulation, User,
)
from loguru import logger
from finacialsim_saas.errors import NotFoundError

UTC = timezone.utc


def _vehicle_desc(snapshot_json: dict) -> str:
    """Safely extract vehicle description from snapshot JSON."""
    try:
        veiculo = snapshot_json.get("veiculo")
        if veiculo and isinstance(veiculo, dict):
            return veiculo.get("descricao", "")
    except Exception:
        pass
    return ""


def _effective_status(p: ParcelaPayment) -> str:
    """Returns 'overdue' for open parcelas past due; otherwise p.status.value."""
    if p.status == ParcelaPaymentStatus.open and p.vencimento < date.today():
        return "overdue"
    return p.status.value


def _calculate_overdue_amount(
    valor_parcela: Decimal,
    dias_atraso: int,
    multa_pct: Decimal,
    juros_diario_pct: Decimal,
    carencia_dias: int,
) -> dict:
    """Pure function: computes real-time encargos estimate for an overdue parcela."""
    dias_com_encargos = max(dias_atraso - carencia_dias, 0)
    if dias_com_encargos > 0:
        multa = (valor_parcela * multa_pct / 100).quantize(Decimal("0.01"))
    else:
        multa = Decimal("0.00")
    juros = (valor_parcela * juros_diario_pct / 100 * dias_com_encargos).quantize(Decimal("0.01"))
    valor_corrigido = valor_parcela + multa + juros
    return {
        "multa": str(multa),
        "juros_acumulado": str(juros),
        "valor_corrigido": str(valor_corrigido),
        "dias_atraso": dias_atraso,
        "estimativa": True,
    }


class ParcelaService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_for_customer(self, ctx: RequestContext) -> list[dict[str, Any]]:
        """Returns approved proposals with parcela status counts for the customer."""
        if ctx.client_id is None:
            return []

        proposals = list(
            await self._s.scalars(
                select(Proposal)
                .join(Simulation, Proposal.simulation_id == Simulation.id)
                .where(
                    Proposal.tenant_id == ctx.tenant_id,
                    Proposal.status == ProposalStatus.aprovada,
                    Simulation.client_id == ctx.client_id,
                )
                .order_by(Proposal.aprovado_em.desc())
            )
        )

        result = []
        for proposal in proposals:
            parcelas = list(
                await self._s.scalars(
                    select(ParcelaPayment).where(
                        ParcelaPayment.proposal_id == proposal.id
                    )
                )
            )
            counts: dict[str, int] = {"open": 0, "paid": 0, "overdue": 0, "canceled": 0}
            for p in parcelas:
                key = _effective_status(p)
                counts[key] = counts.get(key, 0) + 1

            result.append(
                {
                    "proposal_id": str(proposal.id),
                    "codigo": proposal.codigo,
                    "veiculo": _vehicle_desc(proposal.snapshot_json),
                    "status_counts": counts,
                    "total_parcelas": len(parcelas),
                    "aprovado_em": (
                        proposal.aprovado_em.isoformat() if proposal.aprovado_em else None
                    ),
                }
            )
        return result

    async def get_schedule(
        self, proposal_id: uuid.UUID, ctx: RequestContext
    ) -> dict[str, Any]:
        """Returns full parcela schedule; verifies customer ownership."""
        if ctx.client_id is None:
            raise NotFoundError(f"proposal {proposal_id} not found")

        proposal = await self._s.get(Proposal, proposal_id)
        if proposal is None or proposal.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"proposal {proposal_id} not found")

        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim is None or sim.client_id != ctx.client_id:
            raise NotFoundError(f"proposal {proposal_id} not found")

        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment)
                .where(ParcelaPayment.proposal_id == proposal_id)
                .order_by(ParcelaPayment.parcela_num)
            )
        )

        from finacialsim_saas.services.rules_service import RulesService
        rules = await RulesService(self._s).get_rules(proposal.tenant_id)
        multa_pct = Decimal(str(rules.get("inadimplencia_multa_pct", "0.00")))
        juros_diario_pct = Decimal(str(rules.get("inadimplencia_juros_diario_pct", "0.00")))
        carencia_dias = int(rules.get("inadimplencia_carencia_dias", 0))

        today = date.today()
        next_open_id = None
        parcela_list = []
        for p in parcelas:
            status = _effective_status(p)
            if next_open_id is None and status in ("open", "overdue"):
                next_open_id = str(p.id)
            item: dict[str, Any] = {
                "id": str(p.id),
                "parcela_num": p.parcela_num,
                "vencimento": p.vencimento.isoformat(),
                "valor_parcela": str(p.valor_parcela),
                "status": status,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                "paid_amount": str(p.paid_amount) if p.paid_amount else None,
            }
            if status == "overdue":
                dias_atraso = (today - p.vencimento).days
                item["encargos"] = _calculate_overdue_amount(
                    p.valor_parcela, dias_atraso, multa_pct, juros_diario_pct, carencia_dias
                )
            parcela_list.append(item)

        return {
            "proposal_id": str(proposal.id),
            "codigo": proposal.codigo,
            "veiculo": _vehicle_desc(proposal.snapshot_json),
            "next_open_parcela_id": next_open_id,
            "parcelas": parcela_list,
        }

    async def get_parcela(
        self, parcela_id: uuid.UUID, ctx: RequestContext
    ) -> ParcelaPayment:
        """Returns a single parcela after verifying customer ownership."""
        if ctx.client_id is None:
            raise NotFoundError(f"parcela {parcela_id} not found")

        parcela = await self._s.get(ParcelaPayment, parcela_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela {parcela_id} not found")

        proposal = await self._s.get(Proposal, parcela.proposal_id)
        if proposal is None:
            raise NotFoundError(f"parcela {parcela_id} not found")

        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim is None or sim.client_id != ctx.client_id:
            raise NotFoundError(f"parcela {parcela_id} not found")

        return parcela

    async def mark_overdue(self) -> None:
        """Flip open parcelas past due to overdue. Called by ARQ cron at 05:00 UTC."""
        today = date.today()

        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment).where(
                    and_(
                        ParcelaPayment.status == ParcelaPaymentStatus.open,
                        ParcelaPayment.vencimento < today,
                    )
                )
            )
        )

        now = datetime.now(UTC)
        for parcela in parcelas:
            parcela.status = ParcelaPaymentStatus.overdue
            self._s.add(
                AuditLog(
                    tenant_id=parcela.tenant_id,
                    acao="parcela_overdue",
                    entidade="parcela_payments",
                    entidade_id=parcela.id,
                    diff_json={
                        "from": "open",
                        "to": "overdue",
                        "vencimento": parcela.vencimento.isoformat(),
                    },
                )
            )
            # Notify customer: parcela overdue
            try:
                from finacialsim_saas.notifications.service import NotificationService
                proposal = await self._s.get(Proposal, parcela.proposal_id)
                if proposal is not None:
                    sim = await self._s.get(Simulation, proposal.simulation_id)
                    if sim is not None and sim.client_id is not None:
                        cu_result = await self._s.execute(
                            select(User).where(
                                User.client_id == sim.client_id,
                                User.role == Role.customer,
                                User.is_active.is_(True),
                            )
                        )
                        customer = cu_result.scalar_one_or_none()
                        if customer and "@" in (customer.email or ""):
                            dias_atraso = (date.today() - parcela.vencimento).days
                            await NotificationService(self._s).enqueue(
                                template_key="portal.parcela_overdue",
                                payload={
                                    "user_name": customer.name,
                                    "valor_parcela": str(parcela.valor_parcela),
                                    "parcela_num": parcela.parcela_num,
                                    "dias_atraso": max(dias_atraso, 1),
                                },
                                target_email=customer.email,
                                tenant_id=parcela.tenant_id,
                                idempotency_key=f"portal.parcela_overdue:{parcela.id}:{date.today().isoformat()}",
                            )
            except Exception as exc:
                logger.warning("parcela_overdue notification failed", exc=str(exc))

        await self._s.commit()
