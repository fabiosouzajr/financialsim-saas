import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.errors import AppError
from finacialsim_saas.middleware.logging import configure_logging
from finacialsim_saas.services.fipe_service import build_fipe_chain
from finacialsim_saas.settings import get_settings

# Shared state accessed by route handlers — populated during lifespan startup
app_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_env)
    engine = build_engine(str(settings.database_url))
    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.fipe_chain = build_fipe_chain(app.state.session_factory)
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
    await engine.dispose()
    logger.info("shutdown")


app = FastAPI(title="FinacialSim SaaS", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attaches a UUID to every request and logs method, path, status, and latency."""
    import time

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    with logger.contextualize(request_id=request_id):
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request",
            method=request.method,
            path=str(request.url.path),
            status=response.status_code,
            latency_ms=latency_ms,
        )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Converts any AppError subclass into the standard error response shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


from finacialsim_saas.api.health import router as health_router                        # noqa: E402
from finacialsim_saas.api.auth import router as auth_router                            # noqa: E402
from finacialsim_saas.api.users import router as users_router                          # noqa: E402
from finacialsim_saas.api.business_rules import router as business_rules_router        # noqa: E402
from finacialsim_saas.api.simulations import router as simulations_router              # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(business_rules_router)
app.include_router(simulations_router)
