"""BACEN SGS primary provider for SELIC, CDI, IPCA, Tx BACEN veículos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.bacen.schema import IndicatorPoint, Unidade
from app.integrations.base import Err, Ok
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://api.bcb.gov.br/dados/serie"

# (sgs_codigo, unidade)
CODIGOS: dict[str, tuple[int, Unidade]] = {
    "SELIC_META": (432, "pct_aa"),
    "SELIC_DIARIA": (11, "pct_ad"),
    "CDI": (12, "pct_ad"),
    "IPCA": (433, "pct_am"),
    "TX_BACEN_VEIC": (20714, "pct_am"),
}


class BcbSgsProvider:
    name = "bcb_sgs"

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
            f"?formato=json&dataInicial={di.strftime('%d/%m/%Y')}"
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
                pct = Decimal(entry["valor"])
                if pct < 0 or pct > 100:
                    return Err(f"invalid_value_out_of_range: {pct}")
                fracao = (pct / Decimal("100")).quantize(Decimal("0.00000001"))
                points.append(IndicatorPoint(
                    codigo=codigo,
                    data_referencia=ref_date,
                    valor_fracao=fracao,
                    unidade=unidade,
                    fonte="bcb_sgs",
                ))
            return Ok(points)
        except httpx.HTTPError:
            raise  # tenacity retries this
        except (KeyError, ValueError, IndexError, TypeError) as e:
            return Err(f"parse_error: {e}")
