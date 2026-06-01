from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.http import get_json, http_err_callback
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint

BASE_URL = "https://brasilapi.com.br/api/taxas/v1"

# TX_BACEN_VEIC not supported by BrasilAPI — omit intentionally
ALIAS: dict[str, tuple[str, str]] = {
    "SELIC": ("Selic", "pct_aa"),
    "CDI": ("CDI", "pct_ad"),
    "IPCA": ("IPCA", "pct_am"),
}


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
        entry = ALIAS.get(codigo)
        if entry is None:
            return Err(f"unsupported_codigo_brasilapi: {codigo}")
        alias, unidade = entry
        try:
            data = await get_json(f"{BASE_URL}/{alias}", self._client)
            valor = Decimal(str(data["valor"]))
            if valor < 0 or valor > 100:
                return Err(f"invalid_value: {valor}")
            point = IndicatorPoint(
                codigo=codigo,
                data_referencia=date.today(),
                valor=valor,
                unidade=unidade,
                fonte="bacen_brasilapi",
            )
            return Ok([point])
        except httpx.HTTPError:
            raise
        except (KeyError, ValueError) as e:
            return Err(f"parse_error: {e}")
