"""ProposalService — manages the full proposal lifecycle."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AmortizationRow, Client, NotificationsOutbox, ParcelaPayment,
    ParcelaPaymentStatus, Proposal, ProposalRenderStatus, ProposalStatus,
    Role, Simulation, SimulationExtra, SimulationFee, SimulationStatus,
    Tenant, User, Vehicle,
)
from finacialsim_saas.errors import ConflictError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.proposals import (
    ProposalListItem, ProposalListPage, PropostaSnapshot, build_snapshot,
)
from finacialsim_saas.services.audit_service import AuditService
from finacialsim_saas.storage import StorageBackend

UTC = timezone.utc


class ProposalService:
    def __init__(self, session: AsyncSession, arq: Any, storage: StorageBackend) -> None:
        self._s = session
        self._arq = arq
        self._storage = storage
        self._audit = AuditService(session)

    async def _get_proposal_owned(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._s.get(Proposal, proposal_id)
        if proposal is None or proposal.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"proposal {proposal_id} not found")
        return proposal

    def _can_act_on(self, proposal: Proposal, ctx: RequestContext) -> bool:
        if ctx.role in (Role.admin, Role.manager):
            return True
        return proposal.gerado_por == ctx.user_id

    async def create(self, simulation_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        sim = await self._s.get(Simulation, simulation_id)
        if sim is None or sim.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"simulation {simulation_id} not found")
        if sim.status != SimulationStatus.confirmado:
            raise ValidationError("simulation must be confirmado to generate a proposal")

        existing = await self._s.scalar(
            select(Proposal).where(
                Proposal.tenant_id == ctx.tenant_id,
                Proposal.simulation_id == simulation_id,
            )
        )
        if existing is not None:
            raise ConflictError("a proposal already exists for this simulation")

        fees = list(await self._s.scalars(
            select(SimulationFee).where(SimulationFee.simulation_id == simulation_id)
        ))
        extras = list(await self._s.scalars(
            select(SimulationExtra)
            .where(SimulationExtra.simulation_id == simulation_id)
            .order_by(SimulationExtra.ordem)
        ))
        rows = list(await self._s.scalars(
            select(AmortizationRow)
            .where(AmortizationRow.simulation_id == simulation_id)
            .order_by(AmortizationRow.numero_parcela)
        ))
        client = await self._s.get(Client, sim.client_id) if sim.client_id else None
        vehicle = await self._s.get(Vehicle, sim.vehicle_id) if sim.vehicle_id else None
        tenant = await self._s.get(Tenant, ctx.tenant_id)
        user = await self._s.get(User, ctx.user_id)
        if tenant is None or user is None:
            raise NotFoundError("tenant or user context not found")

        snapshot = build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user)

        year = date.today().year
        count = await self._s.scalar(
            select(func.count(Proposal.id)).where(
                Proposal.tenant_id == ctx.tenant_id,
                Proposal.codigo.like(f"PROP-{year}-%"),
            )
        ) or 0
        codigo = f"PROP-{year}-{count + 1:05d}"

        proposal = Proposal(
            tenant_id=ctx.tenant_id,
            simulation_id=simulation_id,
            codigo=codigo,
            gerado_por=ctx.user_id,
            validade_dias=7,
            snapshot_json=snapshot.model_dump(),
            render_status=ProposalRenderStatus.pending,
            status=ProposalStatus.rascunho,
        )
        self._s.add(proposal)
        await self._s.flush()
        await self._arq.enqueue_job("render_proposta_pdf", str(proposal.id))
        await self._s.commit()
        await self._audit.log("proposta_criada", "proposals", proposal.id, None, ctx)
        return proposal

    async def get(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        return await self._get_proposal_owned(proposal_id, ctx)

    async def list(
        self,
        ctx: RequestContext,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProposalListPage:
        q = select(Proposal).where(Proposal.tenant_id == ctx.tenant_id)
        if status:
            q = q.where(Proposal.status == ProposalStatus(status))
        if cursor:
            import base64
            import json
            cur = json.loads(base64.b64decode(cursor))
            q = q.where(Proposal.gerado_em < cur["ts"])
        q = q.order_by(Proposal.gerado_em.desc()).limit(limit + 1)
        results = list(await self._s.scalars(q))
        has_more = len(results) > limit
        items = results[:limit]
        next_cursor = None
        if has_more:
            import base64
            import json
            next_cursor = base64.b64encode(
                json.dumps({"ts": items[-1].gerado_em.isoformat()}).encode()
            ).decode()
        return ProposalListPage(
            items=[
                ProposalListItem.model_validate(p)
                for p in items
            ],
            next_cursor=next_cursor,
        )

    async def download_pdf(
        self, proposal_id: uuid.UUID, kind: str, ctx: RequestContext
    ) -> str:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        key = proposal.pdf_key if kind == "proposta" else proposal.carne_key
        if key is None:
            raise ValidationError(f"{kind} PDF not available yet")
        return await self._storage.signed_url(key, expires_in=300)

    async def approve(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if proposal.status != ProposalStatus.ready:
            raise ValidationError("proposal must be ready to approve")
        if not self._can_act_on(proposal, ctx):
            raise TenantAccessError("insufficient permissions to approve this proposal")

        snap = PropostaSnapshot.model_validate(proposal.snapshot_json)
        now = datetime.now(UTC)

        for row in snap.cronograma:
            self._s.add(
                ParcelaPayment(
                    tenant_id=ctx.tenant_id,
                    proposal_id=proposal.id,
                    parcela_num=row.numero,
                    vencimento=date.fromisoformat(row.venc),
                    valor_parcela=Decimal(row.parcela_total),
                    status=ParcelaPaymentStatus.pending,
                )
            )

        recipient = ""
        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim and sim.client_id:
            client = await self._s.get(Client, sim.client_id)
            if client:
                recipient = client.email or ""
        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                type="customer_invite",
                recipient=recipient,
                payload={"proposal_id": str(proposal.id)},
            )
        )

        proposal.status = ProposalStatus.aprovada
        proposal.aprovado_por = ctx.user_id
        proposal.aprovado_em = now
        await self._s.commit()
        await self._audit.log("proposta_aprovada", "proposals", proposal.id, None, ctx)
        return proposal

    async def cancel(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if proposal.status != ProposalStatus.aprovada:
            raise ValidationError("only approved proposals can be cancelled")
        if not self._can_act_on(proposal, ctx):
            raise TenantAccessError("insufficient permissions to cancel this proposal")

        now = datetime.now(UTC)

        await self._s.execute(
            update(ParcelaPayment)
            .where(ParcelaPayment.proposal_id == proposal.id)
            .values(status=ParcelaPaymentStatus.canceled)
        )

        # TODO Phase 6: deactivate customer User row linked to this proposal
        # TODO Phase 6: cancel open pix_charges via pix_service.cancel_charge()

        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                type="proposal_cancelled",
                recipient="",
                payload={"proposal_id": str(proposal.id)},
            )
        )

        proposal.status = ProposalStatus.cancelada
        proposal.cancelado_por = ctx.user_id
        proposal.cancelado_em = now
        await self._s.commit()
        await self._audit.log("proposta_cancelada", "proposals", proposal.id, None, ctx)
        return proposal

    async def create_carne(self, proposal_id: uuid.UUID, ctx: RequestContext) -> Proposal:
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if proposal.status != ProposalStatus.aprovada:
            raise ValidationError("carnê can only be generated for approved proposals")
        await self._arq.enqueue_job("render_carne_pdf", str(proposal.id))
        return proposal

    async def re_render(
        self, proposal_id: uuid.UUID, kind: str, ctx: RequestContext
    ) -> Proposal:
        if ctx.role != Role.admin:
            raise TenantAccessError("only admins can re-render proposals")
        proposal = await self._get_proposal_owned(proposal_id, ctx)
        if kind == "proposta":
            proposal.render_status = ProposalRenderStatus.pending
            proposal.render_error = None
            await self._s.commit()
            await self._arq.enqueue_job("render_proposta_pdf", str(proposal.id))
        else:
            await self._arq.enqueue_job("render_carne_pdf", str(proposal.id))
        return proposal
