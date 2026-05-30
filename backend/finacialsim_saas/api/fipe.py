from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx
from finacialsim_saas.schemas.fipe import FipeBrandItem, FipeModelItem, FipePriceOut, FipeYearItem
from finacialsim_saas.services.fipe_service import FipeService

router = APIRouter(prefix="/api/v1/fipe", tags=["fipe"])

_VALID_TIPOS = {"carro", "moto", "caminhao"}


@router.get("/types")
async def get_fipe_types(
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
) -> list[str]:
    return list(_VALID_TIPOS)


@router.get("/brands", response_model=list[FipeBrandItem])
async def get_brands(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
) -> list[FipeBrandItem]:
    svc = FipeService(request.app.state.fipe_chain)
    return [FipeBrandItem(**b) for b in await svc.get_brands(tipo)]


@router.get("/models", response_model=list[FipeModelItem])
async def get_models(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
    brand_id: str = Query(...),
) -> list[FipeModelItem]:
    svc = FipeService(request.app.state.fipe_chain)
    return [FipeModelItem(**m) for m in await svc.get_models(tipo, brand_id)]


@router.get("/years", response_model=list[FipeYearItem])
async def get_years(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
    brand_id: str = Query(...),
    model_id: str = Query(...),
) -> list[FipeYearItem]:
    svc = FipeService(request.app.state.fipe_chain)
    return [FipeYearItem(**y) for y in await svc.get_years(tipo, brand_id, model_id)]


@router.get("/price", response_model=FipePriceOut)
async def get_price(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
    brand_id: str = Query(...),
    model_id: str = Query(...),
    year_id: str = Query(...),
) -> FipePriceOut:
    svc = FipeService(request.app.state.fipe_chain)
    quote = await svc.get_price(tipo, brand_id, model_id, year_id)
    return FipePriceOut(
        tipo=quote.tipo,
        marca=quote.marca,
        marca_id=quote.marca_id,
        modelo=quote.modelo,
        modelo_id=quote.modelo_id,
        ano_modelo=quote.ano_modelo,
        combustivel=quote.combustivel,
        codigo_fipe=quote.codigo_fipe,
        valor=quote.valor,
        mes_referencia=quote.mes_referencia,
        fonte=quote.fonte,
    )
