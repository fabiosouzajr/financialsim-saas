from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import BusinessRule
from finacialsim_saas.errors import AppError

_REQUIRED_RULES = frozenset([
    "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
    "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
    "valor_minimo_financiado", "iof_fixo_pct", "iof_diario_pct",
    "iof_diario_max_dias", "incluir_iof_default",
    "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
    "taxa_por_prazo_curva",
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
