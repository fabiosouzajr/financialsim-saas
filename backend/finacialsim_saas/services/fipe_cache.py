from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.fipe.schema import VehicleQuote
from finacialsim_saas.data.models import FipeCache


class PostgresFipeCache:
    """Wraps a FIPE provider, caching results in the fipe_cache Postgres table."""

    def __init__(
        self,
        provider: Any,
        session_factory: async_sessionmaker,
        listas_ttl_horas: int = 720,
        preco_ttl_horas: int = 24,
    ) -> None:
        self._provider = provider
        self._sf = session_factory
        self._listas_ttl = listas_ttl_horas
        self._preco_ttl = preco_ttl_horas

    @property
    def name(self) -> str:
        return self._provider.name

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        key = _build_key(query)
        async with self._sf() as s:
            row = await _get_row(s, key)
            if row is not None and _is_fresh(row):
                logger.debug("fipe_cache_hit", provider=self.name, **key)
                return Ok(_deserialize(query.get("action", ""), row.payload_json))

        result = await self._provider.fetch(query)
        if result.is_ok:
            ttl = self._preco_ttl if query.get("action") == "price" else self._listas_ttl
            async with self._sf() as s:
                await _upsert(s, key, _serialize(query.get("action", ""), result.value), ttl)
                await s.commit()
            logger.debug("fipe_cache_miss", provider=self.name, **key)
        return result


def _build_key(query: dict) -> dict:
    return {
        "tipo": query.get("tipo", ""),
        "acao": query.get("action", ""),
        "marca_id": str(query.get("brand_id", "")),
        "modelo_id": str(query.get("model_id", "")),
        "ano_id": str(query.get("year_id", "")),
    }


def _is_fresh(row: FipeCache) -> bool:
    age_hours = (datetime.now(timezone.utc) - row.coletado_em).total_seconds() / 3600
    return age_hours < row.ttl_horas


async def _get_row(session, key: dict) -> FipeCache | None:
    stmt = select(FipeCache).where(
        FipeCache.tipo == key["tipo"],
        FipeCache.acao == key["acao"],
        FipeCache.marca_id == key["marca_id"],
        FipeCache.modelo_id == key["modelo_id"],
        FipeCache.ano_id == key["ano_id"],
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _upsert(session, key: dict, payload: dict, ttl_horas: int) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(FipeCache)
        .values(
            tipo=key["tipo"],
            acao=key["acao"],
            marca_id=key["marca_id"],
            modelo_id=key["modelo_id"],
            ano_id=key["ano_id"],
            payload_json=payload,
            coletado_em=now,
            ttl_horas=ttl_horas,
        )
        .on_conflict_do_update(
            constraint="uq_fipe_cache_key",
            set_={"payload_json": payload, "coletado_em": now, "ttl_horas": ttl_horas},
        )
    )
    await session.execute(stmt)


def _serialize(action: str, value: Any) -> dict:
    if action == "price" and isinstance(value, VehicleQuote):
        return {
            "tipo": value.tipo,
            "marca": value.marca,
            "marca_id": value.marca_id,
            "modelo": value.modelo,
            "modelo_id": value.modelo_id,
            "ano_modelo": value.ano_modelo,
            "combustivel": value.combustivel,
            "codigo_fipe": value.codigo_fipe,
            "valor": str(value.valor),
            "mes_referencia": value.mes_referencia,
            "fonte": value.fonte,
            "raw_payload": value.raw_payload,
        }
    return {"items": value}


def _deserialize(action: str, payload: dict) -> Any:
    if action == "price":
        return VehicleQuote(
            tipo=payload["tipo"],
            marca=payload["marca"],
            marca_id=payload["marca_id"],
            modelo=payload["modelo"],
            modelo_id=payload["modelo_id"],
            ano_modelo=int(payload["ano_modelo"]),
            combustivel=payload["combustivel"],
            codigo_fipe=payload["codigo_fipe"],
            valor=Decimal(payload["valor"]),
            mes_referencia=payload["mes_referencia"],
            fonte=payload["fonte"],
            raw_payload=payload.get("raw_payload", {}),
        )
    return payload["items"]
