"""Portal API endpoints — customer-facing (role=customer JWT required)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import User
from finacialsim_saas.pix.deps import get_pix_provider
from finacialsim_saas.services.parcela_service import ParcelaService
from finacialsim_saas.services.proposal_service import ProposalService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/portal", tags=["portal"])

_CustomerCtx = Annotated[RequestContext, Depends(require_role("customer"))]
_Session = Annotated[AsyncSession, Depends(get_db_session)]


def _parcela_svc(session: AsyncSession) -> ParcelaService:
    return ParcelaService(session)


def _pix_svc(request: Request, session: AsyncSession):
    from finacialsim_saas.pix.service import PixService
    settings = get_settings()
    return PixService(session, get_pix_provider(settings), get_storage_backend(settings))


def _proposal_svc(request: Request, session: AsyncSession) -> ProposalService:
    settings = get_settings()
    return ProposalService(
        session=session,
        arq=request.app.state.arq,
        storage=get_storage_backend(settings),
    )


@router.get("/me")
async def get_portal_me(
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    user = await session.get(User, ctx.user_id)
    if user is None:
        from finacialsim_saas.errors import NotFoundError
        raise NotFoundError("user not found")
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "client_id": str(user.client_id) if user.client_id else None,
    }


@router.get("/financiamentos")
async def list_financiamentos(
    ctx: _CustomerCtx,
    session: _Session,
) -> list:
    return await _parcela_svc(session).list_for_customer(ctx)


@router.get("/financiamentos/{proposal_id}")
async def get_financiamento(
    proposal_id: uuid.UUID,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    return await _parcela_svc(session).get_schedule(proposal_id, ctx)


@router.get("/parcelas/{parcela_id}")
async def get_parcela(
    parcela_id: uuid.UUID,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    from datetime import date
    from decimal import Decimal
    from finacialsim_saas.services.parcela_service import _calculate_overdue_amount, _effective_status
    from finacialsim_saas.services.rules_service import RulesService

    svc = _parcela_svc(session)
    p = await svc.get_parcela(parcela_id, ctx)
    effective = _effective_status(p)
    resp: dict = {
        "id": str(p.id),
        "parcela_num": p.parcela_num,
        "vencimento": p.vencimento.isoformat(),
        "valor_parcela": str(p.valor_parcela),
        "status": effective,
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        "paid_amount": str(p.paid_amount) if p.paid_amount else None,
    }
    if effective == "overdue":
        rules = await RulesService(session).get_rules(ctx.tenant_id)
        dias_atraso = (date.today() - p.vencimento).days
        resp["encargos"] = _calculate_overdue_amount(
            p.valor_parcela,
            dias_atraso,
            Decimal(str(rules.get("inadimplencia_multa_pct", "0.00"))),
            Decimal(str(rules.get("inadimplencia_juros_diario_pct", "0.00"))),
            int(rules.get("inadimplencia_carencia_dias", 0)),
        )
    return resp


@router.post("/parcelas/{parcela_id}/pix-charge", status_code=201)
async def create_pix_charge(
    parcela_id: uuid.UUID,
    request: Request,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    svc = _pix_svc(request, session)
    charge, qr_url = await svc.create_charge_for_parcela(parcela_id, ctx)
    return {
        "charge_id": str(charge.id),
        "brcode": charge.brcode,
        "qr_url": qr_url,
        "expires_at": charge.expires_at.isoformat(),
    }


@router.get("/pix-charges/{charge_id}")
async def get_pix_charge(
    charge_id: uuid.UUID,
    request: Request,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    svc = _pix_svc(request, session)
    charge, qr_url = await svc.get_charge(charge_id, ctx)
    return {
        "charge_id": str(charge.id),
        "status": charge.status.value,
        "brcode": charge.brcode,
        "qr_url": qr_url,
        "expires_at": charge.expires_at.isoformat(),
    }


@router.get("/proposals/{proposal_id}/download")
async def download_portal_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: _CustomerCtx,
    session: _Session,
    kind: str = Query(default="proposta"),
) -> RedirectResponse:
    svc = _proposal_svc(request, session)
    url = await svc.download_pdf(proposal_id, kind, ctx)
    return RedirectResponse(url, status_code=302)
