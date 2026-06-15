from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import BusinessRule
from finacialsim_saas.services.audit_service import AuditService

# Single source of truth for all business rule defaults: key → (value, description)
_RULE_DEFAULTS: dict[str, tuple[Any, str]] = {
    "entrada_minima_pct":              ("0.10",    "Percentual mínimo de entrada"),
    "prazo_minimo_meses":              (12,        "Prazo mínimo em meses"),
    "prazo_maximo_meses":              (72,        "Prazo máximo em meses"),
    "taxa_minima_mes":                 ("0.005",   "Taxa mensal mínima"),
    "taxa_maxima_mes":                 ("0.05",    "Taxa mensal máxima"),
    "dias_max_carencia":               (90,        "Dias máximos de carência"),
    "valor_minimo_financiado":         ("5000.00", "Valor mínimo financiado"),
    "iof_fixo_pct":                    ("0.0038",  "IOF fixo percentual"),
    "iof_diario_pct":                  ("0.000082","IOF diário percentual"),
    "iof_diario_max_dias":             (365,       "IOF diário — máximo de dias"),
    "incluir_iof_default":             (True,      "Incluir IOF por padrão"),
    "rateio_ipva_meses_default":       (12,        "Meses de rateio IPVA padrão"),
    "rateio_emplacamento_meses_default":(3,        "Meses de rateio emplacamento padrão"),
    "taxa_por_prazo_curva": ([
        {"ate_meses": 24, "taxa_mensal": "0.0179"},
        {"ate_meses": 36, "taxa_mensal": "0.0199"},
        {"ate_meses": 48, "taxa_mensal": "0.0219"},
        {"ate_meses": 60, "taxa_mensal": "0.0249"},
        {"ate_meses": 72, "taxa_mensal": "0.0279"},
    ], "Curva de taxa sugerida por prazo"),
    "ipva_pct_carro":                  ("0.035",  "IPVA — alíquota carro (% a.a.)"),
    "ipva_pct_moto":                   ("0.030",  "IPVA — alíquota moto (% a.a.)"),
    "ipva_pct_caminhao":               ("0.010",  "IPVA — alíquota caminhão (% a.a.)"),
    "emplacamento_valor_carro":        ("220.46", "Emplacamento — carro (R$)"),
    "emplacamento_valor_moto":         ("188.96", "Emplacamento — moto (R$)"),
    "emplacamento_valor_caminhao":     ("220.46", "Emplacamento — caminhão (R$)"),
    "pix_validade_apos_vencimento_dias": (60,     "Dias de validade do Pix após o vencimento da parcela"),
}

_REQUIRED_RULES = frozenset(_RULE_DEFAULTS.keys())


class RulesService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_rules(self, tenant_id: uuid.UUID) -> dict:
        result = await self._s.execute(
            select(BusinessRule).where(BusinessRule.tenant_id == tenant_id)
        )
        rows = result.scalars().all()
        rules = {r.chave: r.valor_json for r in rows}
        for key in _REQUIRED_RULES - rules.keys():
            rules[key] = _RULE_DEFAULTS[key][0]
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

        audit = AuditService(self._s)
        if rule is None:
            if chave not in _RULE_DEFAULTS:
                from finacialsim_saas.errors import AppError
                raise AppError(f"business rule not found: {chave}")
            _, descricao = _RULE_DEFAULTS[chave]
            rule = BusinessRule(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                chave=chave,
                valor_json=valor,
                descricao=descricao,
                atualizado_em=datetime.now(timezone.utc),
                atualizado_por=ctx.user_id,
            )
            self._s.add(rule)
            await audit.log("create", "business_rule", rule.id, {"valor": valor, "motivo": motivo}, ctx)
        else:
            before = rule.valor_json
            rule.valor_json = valor
            rule.atualizado_em = datetime.now(timezone.utc)
            rule.atualizado_por = ctx.user_id
            diff: dict[str, Any] = {"before": before, "after": valor}
            if motivo is not None:
                diff["motivo"] = motivo
            await audit.log("update", "business_rule", rule.id, diff, ctx)

        if redis is not None:
            await redis.publish("rules.invalidated", str(ctx.tenant_id))
