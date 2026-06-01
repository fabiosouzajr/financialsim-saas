from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from finacialsim_core.integrations.base import ProviderChain
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.integrations.bacen.brasilapi import BrasilApiBacenProvider


@respx.mock
async def test_sgs_primary_ok():
    respx.get(
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
    ).mock(
        return_value=httpx.Response(200, json=[{"data": "01/06/2026", "valor": "10.75"}])
    )
    provider = BcbSgsProvider()
    result = await provider.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_ok
    assert len(result.value) == 1
    assert result.value[0].valor == Decimal("10.75")
    assert result.value[0].codigo == "SELIC"
    assert result.value[0].unidade == "pct_aa"


@respx.mock
async def test_sgs_http_error_returns_err():
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    provider = BcbSgsProvider()
    result = await provider.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_err


@respx.mock
async def test_chain_primary_fail_brasilapi_fallback():
    # SGS fails
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    # BrasilAPI succeeds
    respx.get("https://brasilapi.com.br/api/taxas/v1/Selic").mock(
        return_value=httpx.Response(200, json={"nome": "Selic", "valor": 10.75})
    )
    chain = ProviderChain([BcbSgsProvider(), BrasilApiBacenProvider()])
    result = await chain.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_ok
    assert result.value[0].valor == Decimal("10.75")


@respx.mock
async def test_chain_both_fail_returns_err():
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    respx.get("https://brasilapi.com.br/api/taxas/v1/Selic").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    chain = ProviderChain([BcbSgsProvider(), BrasilApiBacenProvider()])
    result = await chain.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_err


@respx.mock
async def test_tx_bacen_veic_no_brasilapi_fallback():
    # SGS fails for TX_BACEN_VEIC
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.20714/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    # BrasilAPI returns Err for unsupported codigo — no HTTP call needed
    chain = ProviderChain([BcbSgsProvider(), BrasilApiBacenProvider()])
    result = await chain.fetch({
        "codigo": "TX_BACEN_VEIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_err
