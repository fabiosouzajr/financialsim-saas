import httpx
from arq import func
from arq.connections import RedisSettings
from arq.cron import cron

from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.integrations.bacen.brasilapi import BrasilApiBacenProvider
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.settings import get_settings
from finacialsim_saas.workers.notifications import (
    drain_notifications_outbox,
    schedule_parcela_due_reminders,
)
from finacialsim_saas.workers.tasks import (
    mark_overdue_parcelas,
    ping,
    prune_fipe_cache,
    render_carne_pdf,
    render_proposta_pdf,
    update_bacen_indicators,
    verify_provider_health,
)
from finacialsim_core.integrations.base import ProviderChain  # type: ignore[import-untyped]


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
    from finacialsim_saas.storage.deps import get_storage_backend as _get_storage
    ctx["storage_backend"] = _get_storage(settings)
    from finacialsim_saas.pix.deps import get_pix_provider as _get_pix
    ctx["pix_provider"] = _get_pix(settings)


async def shutdown(ctx: dict) -> None:
    await ctx["http_client"].aclose()
    ctx["engine"].dispose()


class WorkerSettings:
    functions = [
        ping,
        func(render_proposta_pdf, timeout=120),
        func(render_carne_pdf, timeout=120),
        drain_notifications_outbox,
        update_bacen_indicators,  # also registered for ad-hoc enqueueing via /indicators/refresh
    ]
    cron_jobs = [
        cron(update_bacen_indicators, hour=12, minute=0),   # 09:00 BRT = 12:00 UTC
        cron(prune_fipe_cache, hour=6, minute=0),            # 03:00 BRT = 06:00 UTC
        cron(verify_provider_health, hour={0, 6, 12, 18}, minute=0),
        cron(mark_overdue_parcelas, hour=5, minute=0),   # 02:00 BRT = 05:00 UTC
        cron(drain_notifications_outbox, second={0, 30}),          # every 30 s
        cron(schedule_parcela_due_reminders, hour=11, minute=0),   # 08:00 BRT = 11:00 UTC
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 60
