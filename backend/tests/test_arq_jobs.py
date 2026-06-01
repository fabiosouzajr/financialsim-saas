import httpx
import respx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncEngine

from arq.connections import RedisSettings, create_pool
from finacialsim_core.integrations.base import ProviderChain
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import IndicatorHistory, ProviderHealth
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.workers.tasks import (
    update_bacen_indicators,
    verify_provider_health,
)


def _make_sgs_response(valor: str = "10.75") -> list[dict]:
    return [{"data": "01/06/2026", "valor": valor}]


@respx.mock
async def test_update_bacen_indicators_populates_db(engine: AsyncEngine, redis_url: str):
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("10.75"))
    )
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("10.65"))
    )
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("4.50"))
    )
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.20714/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("1.85"))
    )

    session_factory = build_session_factory(engine)
    redis_pool = await create_pool(RedisSettings.from_dsn(redis_url))
    http_client = httpx.AsyncClient()
    ctx = {
        "redis": redis_pool,
        "session_factory": session_factory,
        "http_client": http_client,
        "bacen_chain": ProviderChain([BcbSgsProvider(http_client)]),
    }

    await update_bacen_indicators(ctx)

    async with session_factory() as s:
        count = await s.scalar(select(func.count(IndicatorHistory.id)))
    assert count == 4

    # Second call blocked by lock — count stays the same
    await update_bacen_indicators(ctx)

    async with session_factory() as s:
        count2 = await s.scalar(select(func.count(IndicatorHistory.id)))
    assert count2 == 4  # idempotent

    await redis_pool.aclose()
    await http_client.aclose()


@respx.mock
async def test_verify_provider_health_prunes_to_50(engine: AsyncEngine):
    session_factory = build_session_factory(engine)

    # Mock all 4 provider URLs
    respx.get("https://parallelum.com.br/fipe/api/v1/carros/marcas").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get("https://brasilapi.com.br/api/fipe/marcas/v1/carros").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1"
    ).mock(return_value=httpx.Response(200, json=[]))
    respx.get("https://brasilapi.com.br/api/taxas/v1/Selic").mock(
        return_value=httpx.Response(200, json={"valor": 10.75})
    )

    http_client = httpx.AsyncClient()
    ctx = {"http_client": http_client, "session_factory": session_factory}

    # Run 55 times to trigger pruning to 50
    for _ in range(55):
        await verify_provider_health(ctx)

    async with session_factory() as s:
        count = await s.scalar(
            select(func.count(ProviderHealth.id)).where(
                ProviderHealth.provider_name == "fipe_parallelum"
            )
        )
    assert count == 50

    await http_client.aclose()
