from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import ProviderHealth

router = APIRouter(prefix="/api/v1/admin", tags=["admin-health"])


@router.get("/health")
async def admin_health(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> dict[str, Any]:
    from finacialsim_saas.main import app_state  # local import avoids circular dep

    # Postgres
    postgres_status = "ok"
    try:
        async with app_state["engine"].connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        postgres_status = str(exc)[:100]

    # Redis
    redis_status = "ok"
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        redis_status = str(exc)[:100]

    # Provider health: latest row per provider_name (dedup in Python)
    all_rows = (
        await session.scalars(
            select(ProviderHealth).order_by(ProviderHealth.checked_at.desc())
        )
    ).all()
    providers: dict[str, dict] = {}
    for row in all_rows:
        if row.provider_name not in providers:
            providers[row.provider_name] = {
                "success": row.success,
                "latency_ms": row.latency_ms,
                "error": row.error,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            }

    return {"postgres": postgres_status, "redis": redis_status, "providers": providers}
