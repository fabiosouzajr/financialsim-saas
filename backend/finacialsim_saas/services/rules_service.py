from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import BusinessRule
from finacialsim_saas.errors import AppError
from finacialsim_saas.services.audit_service import AuditService

_REQUIRED_RULES = frozenset([
    "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
    "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
    "valor_minimo_financiado", "iof_fixo_pct", "iof_diario_pct",
    "iof_diario_max_dias", "incluir_iof_default",
    "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
    "taxa_por_prazo_curva",
    "ipva_pct_carro", "ipva_pct_moto", "ipva_pct_caminhao",
    "emplacamento_valor_carro", "emplacamento_valor_moto", "emplacamento_valor_caminhao",
])


class RulesService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_rules(self, tenant_id: uuid.UUID) -> dict:
        result = await self._s.execute(
            select(BusinessRule).where(BusinessRule.tenant_id == tenant_id)
        )
        rows = result.scalars().all()
        rules = {r.chave: r.valor_json for r in rows}
        missing = _REQUIRED_RULES - rules.keys()
        if missing:
            raise AppError(
                f"business rule(s) not configured for tenant: {sorted(missing)}"
            )
        return rules

    async def snapshot(self, tenant_id: uuid.UUID) -> dict:
        return await self.get_rules(tenant_id)

    async def update(
        self,
        chave: str,
        valor: Any,
        ctx: RequestContext,
        motivo: str | None = None,
        redis: Any | None = None,
    ) -> None:
        result = await self._s.execute(
            select(BusinessRule).where(
                BusinessRule.tenant_id == ctx.tenant_id,
                BusinessRule.chave == chave,
            )
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise AppError(f"business rule not found: {chave}")

        before = rule.valor_json
        rule.valor_json = valor
        rule.atualizado_em = datetime.now(timezone.utc)
        rule.atualizado_por = ctx.user_id

        diff: dict[str, Any] = {"before": before, "after": valor}
        if motivo is not None:
            diff["motivo"] = motivo

        audit = AuditService(self._s)
        await audit.log("update", "business_rule", rule.id, diff, ctx)

        if redis is not None:
            await redis.publish("rules.invalidated", str(ctx.tenant_id))
