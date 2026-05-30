import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.vehicles import VehicleIn, VehicleListPage, VehicleOut, VehicleStatusUpdate
from finacialsim_saas.services.vehicle_service import VehicleService

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


@router.get("", response_model=VehicleListPage)
async def list_vehicles(
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    placa: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> VehicleListPage:
    fipe_chain = getattr(request.app.state, "fipe_chain", None)
    return await VehicleService(session, fipe_chain).list(
        ctx, status=status, placa=placa, cursor=cursor, limit=limit
    )


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    body: VehicleIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    result = await VehicleService(session).create(body, ctx)
    await session.commit()
    return result


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    return await VehicleService(session).get(vehicle_id, ctx)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    result = await VehicleService(session).update(vehicle_id, body, ctx)
    await session.commit()
    return result


@router.post("/{vehicle_id}/refresh-fipe", response_model=VehicleOut)
async def refresh_fipe(
    vehicle_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    fipe_chain = request.app.state.fipe_chain
    result = await VehicleService(session, fipe_chain).refresh_fipe(vehicle_id, ctx)
    await session.commit()
    return result


@router.post("/{vehicle_id}/status", response_model=VehicleOut)
async def set_vehicle_status(
    vehicle_id: uuid.UUID,
    body: VehicleStatusUpdate,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    result = await VehicleService(session).set_status(vehicle_id, body.status, ctx)
    await session.commit()
    return result
