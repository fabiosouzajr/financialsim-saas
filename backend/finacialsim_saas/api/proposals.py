"""Proposal API endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.schemas.proposals import ProposalCreate, ProposalListPage, ProposalOut
from finacialsim_saas.services.proposal_service import ProposalService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/proposals", tags=["proposals"])


def _svc(request: Request, session: AsyncSession) -> ProposalService:
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.pix.deps import get_pix_provider
    from finacialsim_saas.pix.service import PixService
    settings = get_settings()
    storage = get_storage_backend(settings)
    auth_svc = AuthService(session, settings)
    pix_svc = PixService(session, get_pix_provider(settings), storage)
    return ProposalService(
        session=session,
        arq=request.app.state.arq,
        storage=storage,
        auth_service=auth_svc,
        pix_service=pix_svc,
    )


def _out(p) -> ProposalOut:
    return ProposalOut.model_validate(p)


@router.post("", status_code=202, response_model=ProposalOut)
async def create_proposal(
    body: ProposalCreate,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    return _out(await _svc(request, session).create(body.simulation_id, ctx))


@router.get("", response_model=ProposalListPage)
async def list_proposals(
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> ProposalListPage:
    return await _svc(request, session).list(ctx, status=status, cursor=cursor, limit=limit)


@router.get("/{proposal_id}", response_model=ProposalOut)
async def get_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    return _out(await _svc(request, session).get(proposal_id, ctx))


@router.post("/{proposal_id}/approve", response_model=ProposalOut)
async def approve_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    return _out(await _svc(request, session).approve(proposal_id, ctx))


@router.post("/{proposal_id}/cancel", response_model=ProposalOut)
async def cancel_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    return _out(await _svc(request, session).cancel(proposal_id, ctx))


@router.post("/{proposal_id}/render-carne", status_code=202, response_model=ProposalOut)
async def render_carne(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProposalOut:
    return _out(await _svc(request, session).create_carne(proposal_id, ctx))


@router.get("/{proposal_id}/download")
async def download_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    kind: str = Query(default="proposta"),
) -> RedirectResponse:
    url = await _svc(request, session).download_pdf(proposal_id, kind, ctx)
    return RedirectResponse(url, status_code=302)


@router.post("/{proposal_id}/re-render", response_model=ProposalOut)
async def re_render(
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    kind: str = Query(default="proposta"),
) -> ProposalOut:
    return _out(await _svc(request, session).re_render(proposal_id, kind, ctx))
