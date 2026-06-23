import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.simulations import (
    SimulationCreate, SimulationListPage, SimulationOut,
    SimulationPreviewRequest, SimulationPreviewResponse,
)
from finacialsim_saas.services.simulation_service import SimulationService

router = APIRouter(prefix="/api/v1", tags=["simulations"])


@router.post("/simulations/preview", response_model=SimulationPreviewResponse)
async def preview_simulation(
    body: SimulationPreviewRequest,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationPreviewResponse:
    svc = SimulationService(session)
    return await svc.preview(body, ctx)


@router.post("/simulations", response_model=SimulationOut, status_code=201)
async def create_simulation(
    body: SimulationCreate,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.create(body, ctx)
    await session.commit()
    return result


@router.get("/simulations", response_model=SimulationListPage)
async def list_simulations(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    cliente_nome: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> SimulationListPage:
    svc = SimulationService(session)
    return await svc.list(
        ctx, status=status, cliente_nome=cliente_nome,
        date_from=date_from, date_to=date_to, cursor=cursor, limit=limit,
    )


@router.get("/simulations/{sim_id}", response_model=SimulationOut)
async def get_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    return await svc.get(sim_id, ctx)


@router.patch("/simulations/{sim_id}", response_model=SimulationOut)
async def update_simulation(
    sim_id: uuid.UUID,
    body: SimulationCreate,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.update(sim_id, body, ctx)
    await session.commit()
    return result


@router.post("/simulations/{sim_id}/archive", response_model=SimulationOut)
async def archive_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.archive(sim_id, ctx)
    await session.commit()
    return result


@router.post("/simulations/{sim_id}/confirm", response_model=SimulationOut)
async def confirm_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.confirm(sim_id, ctx)
    await session.commit()
    return result


@router.post("/simulations/{sim_id}/clone", response_model=SimulationOut, status_code=201)
async def clone_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.clone(sim_id, ctx)
    await session.commit()
    return result
