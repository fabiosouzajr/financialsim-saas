"""IndicatorsService - fetch + cache BACEN indicators."""

from __future__ import annotations

from datetime import date

from app.data.repositories import IndicatorRepository
from app.integrations.bacen.schema import IndicatorPoint


class IndicatorsService:
    def __init__(self, session_factory, bacen_chain) -> None:
        self.session_factory = session_factory
        self.chain = bacen_chain

    async def update_indicator(
        self, codigo: str, data_inicial: date, data_final: date,
    ) -> IndicatorPoint | None:
        result = await self.chain.fetch({
            "codigo": codigo,
            "data_inicial": data_inicial,
            "data_final": data_final,
        })
        if not result.is_ok or not result.value:
            return None
        points = result.value
        # Persist in case the chain doesn't auto-cache (defensive)
        with self.session_factory() as session:
            repo = IndicatorRepository(session)
            for pt in points:
                repo.upsert(
                    codigo=pt.codigo, data_referencia=pt.data_referencia,
                    valor=pt.valor_fracao, unidade=pt.unidade, fonte=pt.fonte,
                )
        return points[-1]

    def latest(self, codigo: str) -> IndicatorPoint | None:
        with self.session_factory() as session:
            row = IndicatorRepository(session).get_latest(codigo)
            if row is None:
                return None
            return IndicatorPoint(
                codigo=row.codigo, data_referencia=row.data_referencia,
                valor_fracao=row.valor, unidade=row.unidade, fonte=row.fonte,
            )
