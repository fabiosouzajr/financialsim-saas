"""Cache layer for FIPE providers using the fipe_cache table."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.models import FipeCache
from app.integrations.base import Err, Ok, Provider
from app.integrations.fipe.schema import VehicleQuote


class CachedFipeProvider:
    """Wraps any FIPE Provider with read-through cache.

    Price queries: TTL in hours (default 24).
    List queries: TTL in hours (default 720 = 30 days).
    Absent key fields are stored as "" — never None — to avoid SQLite NULL uniqueness quirks.
    """

    def __init__(
        self,
        wrapped: Provider,
        session_factory,
        listas_ttl_horas: int = 720,
        preco_ttl_horas: int = 24,
    ) -> None:
        self.wrapped = wrapped
        self.session_factory = session_factory
        self.listas_ttl = listas_ttl_horas
        self.preco_ttl = preco_ttl_horas
        self.name = f"cached({wrapped.name})"

    def _key(self, query: dict[str, Any]) -> tuple[str, str, str, str, str]:
        """Return (tipo, acao, marca_id, modelo_id, ano_id) with "" for absent fields."""
        tipo = query.get("tipo", "")
        action = query.get("action", "")
        if action == "brands":
            return (tipo, "brands", "", "", "")
        if action == "models":
            return (tipo, "models", str(query.get("brand_id", "")), "", "")
        if action == "years":
            return (
                tipo, "years",
                str(query.get("brand_id", "")),
                str(query.get("model_id", "")),
                "",
            )
        if action == "price":
            return (
                tipo, "price",
                str(query.get("brand_id", query.get("codigo_fipe", ""))),
                str(query.get("model_id", "")),
                str(query.get("year_id", "")),
            )
        return (tipo, action, "", "", "")

    def _ttl(self, query: dict[str, Any]) -> int:
        return self.preco_ttl if query.get("action") == "price" else self.listas_ttl

    def _deserialize(self, acao: str, payload_json: str) -> Any:
        data = json.loads(payload_json)
        if acao == "price" and isinstance(data, dict):
            return VehicleQuote(
                tipo=data["tipo"],  # type: ignore[arg-type]
                marca=data["marca"],
                marca_id=data["marca_id"],
                modelo=data["modelo"],
                modelo_id=data["modelo_id"],
                ano_modelo=data["ano_modelo"],
                combustivel=data["combustivel"],
                codigo_fipe=data["codigo_fipe"],
                valor=Decimal(data["valor"]),
                mes_referencia=data["mes_referencia"],
                fonte=data["fonte"],
                raw_payload=data.get("raw_payload", {}),
            )
        return data

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        tipo, acao, marca_id, modelo_id, ano_id = self._key(query)
        with self.session_factory() as session:
            row = session.query(FipeCache).filter_by(
                tipo=tipo, acao=acao, marca_id=marca_id, modelo_id=modelo_id, ano_id=ano_id,
            ).first()
            if row is not None:
                age = datetime.utcnow() - row.coletado_em
                if age < timedelta(hours=row.ttl_horas):
                    return Ok(self._deserialize(acao, row.payload_json))

        result = await self.wrapped.fetch(query)
        if result.is_ok:
            payload = result.value
            serialized = json.dumps(
                asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload,
                default=str,
            )
            with self.session_factory() as session:
                row = session.query(FipeCache).filter_by(
                    tipo=tipo, acao=acao, marca_id=marca_id, modelo_id=modelo_id, ano_id=ano_id,
                ).first()
                if row is not None:
                    row.payload_json = serialized
                    row.coletado_em = datetime.utcnow()
                    row.ttl_horas = self._ttl(query)
                    session.commit()
                else:
                    row = FipeCache(
                        tipo=tipo, acao=acao, marca_id=marca_id,
                        modelo_id=modelo_id, ano_id=ano_id,
                        payload_json=serialized, ttl_horas=self._ttl(query),
                    )
                    try:
                        session.add(row)
                        session.commit()
                    except IntegrityError:
                        session.rollback()
        return result
