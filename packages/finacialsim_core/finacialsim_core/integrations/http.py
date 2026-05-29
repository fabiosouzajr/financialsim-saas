"""Shared HTTP helper and tenacity callback for all providers."""

from __future__ import annotations

from typing import Any

import httpx

from app.integrations.base import Err


async def get_json(url: str, client: httpx.AsyncClient | None = None) -> Any:
    owned = client is None
    client = client or httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "FinacialSim/0.1"})
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    finally:
        if owned:
            await client.aclose()


def http_err_callback(retry_state) -> Err:
    """tenacity retry_error_callback — converts final HTTPError to Err."""
    return Err(f"http_error: {retry_state.outcome.exception()}")
