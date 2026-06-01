import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.integrations.bacen.brasilapi import BrasilApiBacenProvider
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.settings import get_settings
from finacialsim_saas.workers.tasks import (
    ping,
    prune_fipe_cache,
    update_bacen_indicators,
    verify_provider_health,
)
from finacialsim_core.integrations.base import ProviderChain


def get_redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings.from_dsn(str(s.redis_url))


async def startup(ctx: dict) -> None:
    settings = get_settings()
    engine = build_engine(str(settings.database_url))
    ctx["engine"] = engine
    ctx["session_factory"] = build_session_factory(engine)
    ctx["http_client"] = httpx.AsyncClient(timeout=10.0)
    ctx["bacen_chain"] = ProviderChain([
        BcbSgsProvider(ctx["http_client"]),
        BrasilApiBacenProvider(ctx["http_client"]),
    ])


async def shutdown(ctx: dict) -> None:
    await ctx["http_client"].aclose()
    ctx["engine"].dispose()


class WorkerSettings:
    functions = [ping]
    cron_jobs = [
        cron(update_bacen_indicators, hour=12, minute=0),   # 09:00 BRT = 12:00 UTC
        cron(prune_fipe_cache, hour=6, minute=0),            # 03:00 BRT = 06:00 UTC
        cron(verify_provider_health, hour={0, 6, 12, 18}, minute=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 60
