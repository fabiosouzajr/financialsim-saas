"""BACEN cache — persists fetched points to indicators_history; read-through with TTL."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.data.models import IndicatorHistory
from app.data.repositories import IndicatorRepository
from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Err, Ok, Provider


class CachedBacenProvider:
    """Wraps a BACEN Provider.

    Read-through: skips the network call when
      - query has a data_final, AND
      - the latest cached entry covers data_final (data_final <= latest.data_referencia), AND
      - that entry is within TTL (latest.data_referencia >= today - ttl_horas/24)

    Write-through: on a cache miss, persists all returned IndicatorPoints to indicators_history.
    """

    def __init__(self, wrapped: Provider, session_factory, ttl_horas: int = 24) -> None:
        self.wrapped = wrapped
        self.session_factory = session_factory
        self.ttl_horas = ttl_horas
        self.name = f"cached({wrapped.name})"

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        data_final: date | None = query.get("data_final")
        data_inicial: date | None = query.get("data_inicial")

        if data_final is not None:
            with self.session_factory() as session:
                repo = IndicatorRepository(session)
                latest = repo.get_latest(codigo)
                if latest is not None:
                    cutoff = date.today() - timedelta(hours=self.ttl_horas / 24)
                    if data_final <= latest.data_referencia and latest.data_referencia >= cutoff:
                        rows = (
                            session.query(IndicatorHistory)
                            .filter(
                                IndicatorHistory.codigo == codigo,
                                IndicatorHistory.data_referencia >= data_inicial,
                                IndicatorHistory.data_referencia <= data_final,
                            )
                            .all()
                        )
                        points = [
                            IndicatorPoint(
                                codigo=r.codigo,
                                data_referencia=r.data_referencia,
                                valor_fracao=r.valor,
                                unidade=r.unidade,  # type: ignore[arg-type]
                                fonte=r.fonte,
                            )
                            for r in rows
                        ]
                        return Ok(points)

        result = await self.wrapped.fetch(query)
        if result.is_ok:
            with self.session_factory() as session:
                repo = IndicatorRepository(session)
                for pt in result.value:
                    repo.upsert(
                        codigo=pt.codigo,
                        data_referencia=pt.data_referencia,
                        valor=pt.valor_fracao,
                        unidade=pt.unidade,
                        fonte=pt.fonte,
                    )
        return result
