from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.schemas.indicators import IndicatorOut, SeriesOut
from finacialsim_saas.services.indicators_service import IndicatorsService

router = APIRouter(prefix="/api/v1", tags=["indicators"])


@router.get("/indicators", response_model=list[IndicatorOut])
async def list_indicators(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[IndicatorOut]:
    return await IndicatorsService(session).latest_all()


@router.get("/indicators/{codigo}/series", response_model=SeriesOut)
async def get_indicator_series(
    codigo: str,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    range: str = Query(default="12m"),
) -> SeriesOut:
    svc = IndicatorsService(session)
    points = await svc.series(codigo, range)
    return SeriesOut(codigo=codigo, range=range, points=points)


@router.post("/indicators/refresh", status_code=202)
async def refresh_indicators(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    request: Request,
) -> dict[str, bool]:
    redis = request.app.state.redis
    await redis.enqueue_job("update_bacen_indicators")
    return {"enqueued": True}
