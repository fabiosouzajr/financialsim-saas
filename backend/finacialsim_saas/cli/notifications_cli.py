import asyncio
import uuid
from typing import Annotated

import typer

notifications_app = typer.Typer(help="Notification management commands")


def _build_ctx():
    """Build a minimal ARQ-style ctx dict for running drain jobs from CLI."""
    import redis.asyncio as aioredis
    from finacialsim_saas.data.database import build_engine, build_session_factory
    from finacialsim_saas.settings import get_settings

    settings = get_settings()
    engine = build_engine(str(settings.database_url))
    return {
        "engine": engine,
        "session_factory": build_session_factory(engine),
        "redis": aioredis.from_url(str(settings.redis_url), decode_responses=True),
    }


@notifications_app.command("drain")
def notifications_drain():
    """Ad-hoc drain of the notifications outbox (bypasses Redis lock)."""
    from finacialsim_saas.workers.notifications import drain_notifications_outbox

    async def _run():
        ctx = _build_ctx()
        # Clear any existing lock so ad-hoc drain always runs
        await ctx["redis"].delete("lock:drain_notifications_outbox")
        await drain_notifications_outbox(ctx)
        await ctx["redis"].aclose()
        ctx["engine"].dispose()

    asyncio.run(_run())
    typer.echo("Drain complete.")


@notifications_app.command("retry")
def notifications_retry(
    outbox_id: Annotated[
        str, typer.Option("--outbox-id", help="UUID of the outbox row to retry")
    ],
):
    """Reset a deadlettered or failed outbox row to pending and drain it immediately."""
    from datetime import datetime, timezone

    row_id = uuid.UUID(outbox_id)

    async def _run():
        from finacialsim_saas.data.database import build_engine, build_session_factory
        from finacialsim_saas.data.models import NotificationsOutbox
        from finacialsim_saas.settings import get_settings
        from finacialsim_saas.workers.notifications import drain_notifications_outbox
        import redis.asyncio as aioredis

        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)

        async with factory() as session:
            row = await session.get(NotificationsOutbox, row_id)
            if row is None:
                typer.echo(f"Error: outbox row {outbox_id} not found.", err=True)
                raise typer.Exit(1)
            now = datetime.now(timezone.utc)
            row.status = "pending"
            row.attempts = 0
            row.last_error = None
            row.scheduled_for = now
            row.updated_at = now
            await session.commit()
            typer.echo(f"Row {outbox_id} reset to pending.")

        r = aioredis.from_url(str(settings.redis_url), decode_responses=True)
        ctx = {"engine": engine, "session_factory": factory, "redis": r}
        await r.delete("lock:drain_notifications_outbox")
        await drain_notifications_outbox(ctx)
        await r.aclose()
        engine.dispose()
        typer.echo("Retry drain complete.")

    asyncio.run(_run())
