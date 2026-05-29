"""Manual FIPE provider — constructs a VehicleQuote from operator-supplied input."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote

_VALID_TIPOS = {"carro", "moto", "caminhao"}


class ManualFipeProvider:
    name = "fipe_manual"

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        if query.get("action") != "price":
            return Err("manual_only_supports_price")
        tipo = query.get("tipo", "carro")
        if tipo not in _VALID_TIPOS:
            return Err(f"invalid_tipo: {tipo!r}. Must be one of {sorted(_VALID_TIPOS)}")
        try:
            quote = VehicleQuote(
                tipo=tipo,  # type: ignore[arg-type]
                marca=query["marca"],
                marca_id=str(query.get("marca_id", "manual")),
                modelo=query["modelo"],
                modelo_id=str(query.get("modelo_id", "manual")),
                ano_modelo=int(query["ano_modelo"]),
                combustivel=query.get("combustivel", ""),
                codigo_fipe=query.get("codigo_fipe", ""),
                valor=Decimal(str(query["valor"])),
                mes_referencia=query.get("mes_referencia", "manual"),
                fonte="manual",
                raw_payload={},
            )
            return Ok(quote)
        except KeyError as e:
            return Err(f"missing_field: {e}")
        except InvalidOperation as e:
            return Err(f"invalid_valor: {e}")
