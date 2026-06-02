from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request):
    """Returns 200 when Postgres and Redis are reachable; 503 if either fails."""
    from finacialsim_saas.main import app_state

    postgres_status = "ok"
    redis_status = "ok"
    overall = "ok"

    try:
        async with app_state["engine"].connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        postgres_status = str(exc)[:100]
        overall = "error"

    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        redis_status = str(exc)[:100]
        overall = "error"

    payload = {"status": overall, "postgres": postgres_status, "redis": redis_status}
    if overall != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/version")
async def version():
    """Returns the git SHA and build timestamp baked into the Docker image."""
    from finacialsim_saas.settings import get_settings

    s = get_settings()
    return {
        "git_sha": s.git_sha,
        "build_time": s.build_time or datetime.now(timezone.utc).isoformat(),
        "app_env": s.app_env,
    }
