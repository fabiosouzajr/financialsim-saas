"""FIPE Parallelum primary provider."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote, parse_brl_price
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://parallelum.com.br/fipe/api/v2"
TIPO_MAP = {"carro": "cars", "moto": "motorcycles", "caminhao": "trucks"}


class ParallelumFipeProvider:
    name = "fipe_parallelum"

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
        tipo_url = TIPO_MAP.get(query.get("tipo", ""), "cars")
        try:
            if action == "brands":
                data = await get_json(f"{BASE_URL}/{tipo_url}/brands", self._client)
                return Ok([{"id": d["code"], "nome": d["name"]} for d in data])
            if action == "models":
                brand_id = query["brand_id"]
                data = await get_json(
                    f"{BASE_URL}/{tipo_url}/brands/{brand_id}/models", self._client
                )
                models = data if isinstance(data, list) else data.get("models", data)
                return Ok([{"id": str(d["code"]), "nome": d["name"]} for d in models])
            if action == "years":
                brand_id = query["brand_id"]
                model_id = query["model_id"]
                data = await get_json(
                    f"{BASE_URL}/{tipo_url}/brands/{brand_id}/models/{model_id}/years",
                    self._client,
                )
                return Ok([{"id": d["code"], "nome": d["name"]} for d in data])
            if action == "price":
                brand_id = query["brand_id"]
                model_id = query["model_id"]
                year_id = query["year_id"]
                data = await get_json(
                    f"{BASE_URL}/{tipo_url}/brands/{brand_id}/models/{model_id}/years/{year_id}",
                    self._client,
                )
                quote = VehicleQuote(
                    tipo=query.get("tipo", "carro"),  # type: ignore[arg-type]
                    marca=data["brand"],
                    marca_id=str(brand_id),
                    modelo=data["model"],
                    modelo_id=str(model_id),
                    ano_modelo=int(data["modelYear"]),
                    combustivel=data.get("fuel", ""),
                    codigo_fipe=data.get("codeFipe", ""),
                    valor=parse_brl_price(data["price"]),
                    mes_referencia=data.get("referenceMonth", ""),
                    fonte="fipe_parallelum",
                    raw_payload=data,
                )
                return Ok(quote)
            return Err(f"unknown_action: {action}")
        except httpx.HTTPError:
            raise  # tenacity retries this
        except KeyError as e:
            return Err(f"missing_field: {e}")
        except Exception as e:
            return Err(f"unexpected: {e}")
