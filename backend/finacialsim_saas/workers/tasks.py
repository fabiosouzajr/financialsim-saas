from __future__ import annotations

import time
from datetime import date, datetime, timezone

import httpx
from loguru import logger
from sqlalchemy import delete, select

from finacialsim_saas.data.models import ProviderHealth
from finacialsim_saas.services.indicators_service import IndicatorsService

UTC = timezone.utc

BACEN_CODIGOS = ["SELIC", "CDI", "IPCA", "TX_BACEN_VEIC"]
PROVIDER_PING_URLS = {
    "fipe_parallelum": "https://parallelum.com.br/fipe/api/v1/carros/marcas",
    "fipe_brasilapi": "https://brasilapi.com.br/api/fipe/marcas/v1/carros",
    "bacen_sgs": (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
    ),
    "bacen_brasilapi": "https://brasilapi.com.br/api/taxas/v1/Selic",
}


async def ping(ctx: dict) -> str:
    """Health-check job. Enqueue it to verify the worker is alive and Redis is reachable."""
    logger.info("ping job executed")
    return "pong"


async def update_bacen_indicators(ctx: dict) -> None:
    today = date.today()
    lock_key = f"lock:update_bacen_indicators:{today.isoformat()}"
    redis = ctx["redis"]
    acquired = await redis.set(lock_key, "1", nx=True, ex=86400)
    if not acquired:
        logger.info("update_bacen_indicators: already ran today, skipping")
        return

    chain = ctx["bacen_chain"]
    session_factory = ctx["session_factory"]
    from datetime import timedelta
    one_year_ago = today - timedelta(days=366)

    async with session_factory() as session:
        svc = IndicatorsService(session)
        for codigo in BACEN_CODIGOS:
            result = await chain.fetch({
                "codigo": codigo,
                "data_inicial": one_year_ago,
                "data_final": today,
            })
            if result.is_ok:
                for point in result.value:
                    await svc.upsert(point)
                await session.commit()
                logger.info(f"update_bacen_indicators: {codigo} ok ({len(result.value)} pts)")
            else:
                logger.warning(f"update_bacen_indicators: {codigo} failed: {result.error}")


async def prune_fipe_cache(ctx: dict) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        now = datetime.now(UTC)
        from sqlalchemy import text
        await session.execute(
            text(
                "DELETE FROM fipe_cache "
                "WHERE coletado_em + ttl_horas * interval '1 hour' < :now"
            ),
            {"now": now},
        )
        await session.commit()
    logger.info("prune_fipe_cache: complete")


async def verify_provider_health(ctx: dict) -> None:
    http: httpx.AsyncClient = ctx["http_client"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        for provider_name, url in PROVIDER_PING_URLS.items():
            start = time.monotonic()
            try:
                resp = await http.get(url, timeout=10.0)
                latency_ms = int((time.monotonic() - start) * 1000)
                success = resp.status_code < 400
                error = None if success else f"HTTP {resp.status_code}"
            except Exception as exc:
                latency_ms = None
                success = False
                error = str(exc)[:200]

            session.add(
                ProviderHealth(
                    provider_name=provider_name,
                    latency_ms=latency_ms,
                    success=success,
                    error=error,
                )
            )
            await session.flush()

            keep_ids = (
                await session.scalars(
                    select(ProviderHealth.id)
                    .where(ProviderHealth.provider_name == provider_name)
                    .order_by(ProviderHealth.checked_at.desc())
                    .limit(50)
                )
            ).all()
            await session.execute(
                delete(ProviderHealth).where(
                    ProviderHealth.provider_name == provider_name,
                    ~ProviderHealth.id.in_(keep_ids),
                )
            )

        await session.commit()
    logger.info("verify_provider_health: complete")
