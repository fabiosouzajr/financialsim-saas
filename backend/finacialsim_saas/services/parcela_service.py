from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, NotificationsOutbox, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalStatus, Simulation,
)
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

        next_open_id = None
        for p in parcelas:
            if _effective_status(p) in ("open", "overdue"):
                next_open_id = str(p.id)
                break

        return {
            "proposal_id": str(proposal.id),
            "codigo": proposal.codigo,
            "veiculo": _vehicle_desc(proposal.snapshot_json),
            "next_open_parcela_id": next_open_id,
            "parcelas": [
                {
                    "id": str(p.id),
                    "parcela_num": p.parcela_num,
                    "vencimento": p.vencimento.isoformat(),
                    "valor_parcela": str(p.valor_parcela),
                    "status": _effective_status(p),
                    "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                    "paid_amount": str(p.paid_amount) if p.paid_amount else None,
                }
                for p in parcelas
            ],
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
            self._s.add(
                NotificationsOutbox(
                    tenant_id=parcela.tenant_id,
                    template_key="parcela_overdue",
                    payload_json={
                        "parcela_id": str(parcela.id),
                        "proposal_id": str(parcela.proposal_id),
                    },
                )
            )

        await self._s.commit()
