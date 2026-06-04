from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.http import get_json, http_err_callback
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint, Unidade

BASE_URL = "https://api.bcb.gov.br/dados/serie"

# Maps our codigo → (SGS series number, unidade)
CODIGOS: dict[str, tuple[int, Unidade]] = {
    "SELIC": (432, "pct_aa"),
    "CDI": (12, "pct_ad"),
    "IPCA": (13522, "pct_12m"),
    "TX_BACEN_VEIC": (20714, "pct_aa"),
}


class BcbSgsProvider:
    name = "bacen_sgs"

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
        if codigo not in CODIGOS:
            return Err(f"unknown_codigo: {codigo}")
        sgs_code, unidade = CODIGOS[codigo]
        di: date = query["data_inicial"]
        df: date = query["data_final"]
        url = (
            f"{BASE_URL}/bcdata.sgs.{sgs_code}/dados"
            f"?formato=json"
            f"&dataInicial={di.strftime('%d/%m/%Y')}"
            f"&dataFinal={df.strftime('%d/%m/%Y')}"
        )
        try:
            raw = await get_json(url, self._client)
            if not isinstance(raw, list):
                return Err(f"unexpected_response: {type(raw).__name__}")
            points: list[IndicatorPoint] = []
            for entry in raw:
                d_parts = entry["data"].split("/")
                ref_date = date(int(d_parts[2]), int(d_parts[1]), int(d_parts[0]))
                valor = Decimal(entry["valor"])
                if valor < 0 or valor > 100:
                    return Err(f"invalid_value_out_of_range: {valor}")
                points.append(IndicatorPoint(
                    codigo=codigo,
                    data_referencia=ref_date,
                    valor=valor,
                    unidade=unidade,
                    fonte="bacen_sgs",
                ))
            return Ok(points)
        except httpx.HTTPError:
            raise  # tenacity retries
        except (KeyError, ValueError, IndexError, TypeError) as e:
            return Err(f"parse_error: {e}")
