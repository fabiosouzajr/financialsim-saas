import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from finacialsim_core.integrations.base import Err, Ok, ProviderChain
from finacialsim_core.integrations.fipe.schema import VehicleQuote
from finacialsim_saas.services.fipe_cache import PostgresFipeCache


def _mock_session_factory(cached_row=None):
    """Returns a session_factory whose sessions return cached_row on SELECT."""
    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=cached_row)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock()
    factory.return_value = mock_session
    return factory, mock_session


@pytest.mark.asyncio
async def test_primary_ok_returns_value():
    factory, _ = _mock_session_factory(cached_row=None)
    provider = AsyncMock()
    brands = [{"id": "21", "nome": "Toyota"}]
    provider.fetch = AsyncMock(return_value=Ok(brands))
    provider.name = "fipe_parallelum"

    cache = PostgresFipeCache(provider, factory)
    result = await cache.fetch({"action": "brands", "tipo": "carro"})

    assert result.is_ok
    assert result.value == brands


@pytest.mark.asyncio
async def test_primary_fail_fallback_ok():
    factory, _ = _mock_session_factory(cached_row=None)
    primary = AsyncMock()
    primary.fetch = AsyncMock(return_value=Err("timeout"))
    primary.name = "fipe_parallelum"
    secondary = AsyncMock()
    brands = [{"id": "21", "nome": "Toyota"}]
    secondary.fetch = AsyncMock(return_value=Ok(brands))
    secondary.name = "fipe_brasilapi"

    p_cache = PostgresFipeCache(primary, factory)
    s_cache = PostgresFipeCache(secondary, factory)
    chain = ProviderChain([p_cache, s_cache])

    result = await chain.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_ok
    assert result.value == brands


@pytest.mark.asyncio
async def test_cache_hit_skips_provider():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    cached = SimpleNamespace(
        payload_json={"items": [{"id": "21", "nome": "Toyota"}]},
        coletado_em=datetime.now(timezone.utc),
        ttl_horas=720,
    )

    factory, _ = _mock_session_factory(cached_row=cached)
    provider = AsyncMock()
    provider.name = "fipe_parallelum"

    cache = PostgresFipeCache(provider, factory)
    result = await cache.fetch({"action": "brands", "tipo": "carro"})

    assert result.is_ok
    provider.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_both_fail_returns_err():
    factory, _ = _mock_session_factory(cached_row=None)
    primary = AsyncMock()
    primary.fetch = AsyncMock(return_value=Err("timeout"))
    primary.name = "fipe_parallelum"
    secondary = AsyncMock()
    secondary.fetch = AsyncMock(return_value=Err("500"))
    secondary.name = "fipe_brasilapi"

    p_cache = PostgresFipeCache(primary, factory)
    s_cache = PostgresFipeCache(secondary, factory)
    chain = ProviderChain([p_cache, s_cache])

    result = await chain.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_err


@pytest.mark.asyncio
async def test_price_serialization_roundtrip():
    from finacialsim_saas.services.fipe_cache import _serialize, _deserialize
    quote = VehicleQuote(
        tipo="carro", marca="Toyota", marca_id="21",
        modelo="Corolla", modelo_id="4591", ano_modelo=2023,
        combustivel="Gasolina", codigo_fipe="005004-4",
        valor=Decimal("120000.00"), mes_referencia="maio/2026",
        fonte="fipe_parallelum", raw_payload={"price": "R$ 120.000,00"},
    )
    serialized = _serialize("price", quote)
    deserialized = _deserialize("price", serialized)
    assert deserialized.valor == Decimal("120000.00")
    assert deserialized.marca == "Toyota"
