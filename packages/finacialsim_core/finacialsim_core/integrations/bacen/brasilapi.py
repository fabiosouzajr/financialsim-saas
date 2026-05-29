"""BACEN fallback — BrasilAPI rates endpoint (single latest value)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Err, Ok
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://brasilapi.com.br/api/taxas/v1"
ALIAS = {"SELIC_META": "Selic", "CDI": "CDI", "IPCA": "IPCA"}


class BrasilApiBacenProvider:
    name = "bacen_brasilapi"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        alias = ALIAS.get(codigo)
        if alias is None:
            return Err(f"unsupported_codigo_brasilapi: {codigo}")
        try:
            data = await get_json(f"{BASE_URL}/{alias}", self._client)
            valor_pct = Decimal(str(data["valor"]))
            if valor_pct < 0 or valor_pct > 100:
                return Err(f"invalid_value: {valor_pct}")
            point = IndicatorPoint(
                codigo=codigo,
                data_referencia=date.today(),
                valor_fracao=(valor_pct / Decimal("100")).quantize(Decimal("0.00000001")),
                unidade="pct_aa" if codigo == "SELIC_META" else "pct_am",
                fonte="brasilapi",
            )
            return Ok([point])
        except httpx.HTTPError:
            raise  # tenacity retries this
        except (KeyError, ValueError) as e:
            return Err(f"parse_error: {e}")
