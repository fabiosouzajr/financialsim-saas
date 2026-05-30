from __future__ import annotations

import httpx
from loguru import logger

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v1/{cep}"


async def lookup_cep(cep: str) -> dict:
    """Proxy CEP lookup to BrasilAPI. Returns {} on any error (fail-open)."""
    clean = "".join(ch for ch in cep if ch.isdigit())
    if len(clean) != 8:
        return {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(BRASILAPI_CEP_URL.format(cep=clean))
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("cep_lookup_failed", cep=clean, error=str(exc))
        return {}
