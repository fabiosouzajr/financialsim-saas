from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Returns 200 when the API can reach the database, 503 otherwise."""
    from finacialsim_saas.main import app_state

    try:
        async with app_state["engine"].connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": str(exc)},
        )


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
