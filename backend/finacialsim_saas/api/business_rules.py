from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.schemas.business_rules import BusinessRulesOut, BusinessRuleUpdateIn, RateCurvePointOut
from finacialsim_saas.services.rules_service import RulesService

router = APIRouter(prefix="/api/v1", tags=["business-rules"])


@router.get("/business-rules", response_model=BusinessRulesOut)
async def get_business_rules(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessRulesOut:
    svc = RulesService(session)
    rules = await svc.get_rules(ctx.tenant_id)
    curva_raw = rules.get("taxa_por_prazo_curva", [])
    return BusinessRulesOut(
        entrada_minima_pct=rules["entrada_minima_pct"],
        prazo_minimo_meses=int(rules["prazo_minimo_meses"]),
        prazo_maximo_meses=int(rules["prazo_maximo_meses"]),
        taxa_minima_mes=rules["taxa_minima_mes"],
        taxa_maxima_mes=rules["taxa_maxima_mes"],
        dias_max_carencia=int(rules["dias_max_carencia"]),
        valor_minimo_financiado=rules["valor_minimo_financiado"],
        iof_fixo_pct=rules["iof_fixo_pct"],
        iof_diario_pct=rules["iof_diario_pct"],
        iof_diario_max_dias=int(rules["iof_diario_max_dias"]),
        incluir_iof_default=bool(rules["incluir_iof_default"]),
        rateio_ipva_meses_default=int(rules["rateio_ipva_meses_default"]),
        rateio_emplacamento_meses_default=int(rules["rateio_emplacamento_meses_default"]),
        taxa_por_prazo_curva=[
            RateCurvePointOut(ate_meses=p["ate_meses"], taxa_mensal=p["taxa_mensal"])
            for p in curva_raw
        ],
        ipva_pct_carro=rules["ipva_pct_carro"],
        ipva_pct_moto=rules["ipva_pct_moto"],
        ipva_pct_caminhao=rules["ipva_pct_caminhao"],
        emplacamento_valor_carro=rules["emplacamento_valor_carro"],
        emplacamento_valor_moto=rules["emplacamento_valor_moto"],
        emplacamento_valor_caminhao=rules["emplacamento_valor_caminhao"],
    )


@router.put("/business-rules/{chave}", status_code=status.HTTP_204_NO_CONTENT)
async def update_business_rule(
    chave: str,
    body: BusinessRuleUpdateIn,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    svc = RulesService(session)
    await svc.update(chave, body.valor, ctx, motivo=body.motivo, redis=redis)
    await session.commit()
