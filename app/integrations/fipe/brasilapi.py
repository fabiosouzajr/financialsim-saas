"""FIPE BrasilAPI fallback provider."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote, parse_brl_price
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://brasilapi.com.br/api/fipe"
TIPO_MAP = {"carro": "carros", "moto": "motos", "caminhao": "caminhoes"}


class BrasilApiFipeProvider:
    name = "fipe_brasilapi"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        action = query.get("action")
        tipo = query.get("tipo", "carro")
        ba_tipo = TIPO_MAP.get(tipo, "carros")
        try:
            if action == "brands":
                data = await get_json(f"{BASE_URL}/marcas/v1/{ba_tipo}", self._client)
                return Ok([{"id": str(d["valor"]), "nome": d["nome"]} for d in data])
            if action == "price":
                codigo = query["codigo_fipe"]
                data = await get_json(f"{BASE_URL}/preco/v1/{codigo}", self._client)
                if not data:
                    return Err("empty_response")
                d = data[0]
                quote = VehicleQuote(
                    tipo=tipo,  # type: ignore[arg-type]
                    marca=d.get("marca", ""),
                    marca_id="",
                    modelo=d.get("modelo", ""),
                    modelo_id="",
                    ano_modelo=int(d.get("anoModelo", 0)),
                    combustivel=d.get("combustivel", ""),
                    codigo_fipe=d.get("codigoFipe", codigo),
                    valor=parse_brl_price(d["valor"]),
                    mes_referencia=d.get("mesReferencia", ""),
                    fonte="fipe_brasilapi",
                    raw_payload=d,
                )
                return Ok(quote)
            return Err(f"unsupported_action_for_brasilapi: {action}")
        except httpx.HTTPError:
            raise  # tenacity retries this
        except KeyError as e:
            return Err(f"missing_field: {e}")
        except Exception as e:
            return Err(f"unexpected: {e}")
