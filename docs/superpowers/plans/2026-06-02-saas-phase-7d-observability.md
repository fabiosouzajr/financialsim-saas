# Phase 7D — Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `/healthz` to check Postgres + Redis (503 on failure, flat response). Enhance `configure_logging` with a JSON production sink, PII masking (patcher + regex), and `contextvars`-based enrichment for `tenant_id` and `user_id`.

**Architecture:** `health.py` imports `app_state["engine"]` and `request.app.state.redis`. Logging changes in `middleware/logging.py`: global patcher masks structured `extra` fields; JSON sink masks free-form message text. Two `contextvars.ContextVar` instances (`_log_tenant_id`, `_log_user_id`) are set in `auth/deps.py` after JWT decoding and read by the patcher.

**Tech Stack:** FastAPI, Loguru 0.7+, asyncio contextvars, Redis aioredis, SQLAlchemy

**Depends on:** Phase 7A (models — needed only because middleware references app startup)

---

## File Map

| Action | File |
|--------|------|
| Modify | `backend/finacialsim_saas/api/health.py` — add Redis check, 503 logic |
| Modify | `backend/finacialsim_saas/middleware/logging.py` — JSON sink, PII masking, contextvars |
| Modify | `backend/finacialsim_saas/auth/deps.py` — set tenant_id/user_id context vars |
| Modify | `backend/tests/test_health.py` — add Redis/503 assertions |

---

### Task 1: Write failing health tests

**Files:**
- Modify: `backend/tests/test_health.py`

- [ ] **Step 1: Add tests for extended healthz**

Open `backend/tests/test_health.py` and append:

```python
async def test_healthz_returns_postgres_and_redis_keys(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert "postgres" in data
    assert "redis" in data
    assert data["postgres"] == "ok"
    assert data["redis"] == "ok"
    assert data["status"] == "ok"
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd backend && uv run pytest tests/test_health.py::test_healthz_returns_postgres_and_redis_keys -v
```

Expected: FAIL — response currently only has `{"status": "ok", "db": "ok"}`.

---

### Task 2: Extend /healthz

**Files:**
- Modify: `backend/finacialsim_saas/api/health.py`

- [ ] **Step 1: Replace healthz endpoint**

Replace the entire `healthz` function in `backend/finacialsim_saas/api/health.py`:

```python
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
```

Add `Request` to the import at the top of the file:

```python
from fastapi import APIRouter, Request
```

- [ ] **Step 2: Run health tests**

```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: All health tests pass including the new one.

---

### Task 3: Enhance configure_logging

**Files:**
- Modify: `backend/finacialsim_saas/middleware/logging.py`

- [ ] **Step 1: Rewrite configure_logging with JSON sink and PII masking**

Replace the entire content of `backend/finacialsim_saas/middleware/logging.py`:

```python
from __future__ import annotations

import contextvars
import json
import re
import sys
from typing import Any

from loguru import logger

# Context vars set by auth/deps.py after JWT decoding — read by the patcher
_log_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_tenant_id", default=None
)
_log_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_user_id", default=None
)

_PII_KEYS = frozenset({"email", "cpf_cnpj", "password", "senha", "target_email", "recipient"})
_PII_PATTERNS = [
    re.compile(r"[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}"),          # email addresses
    re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),              # CPF
    re.compile(r"\d{2}\.?\d{3}\.?\d{3}[/.]?\d{4}-?\d{2}"),   # CNPJ
]


def _mask_string(s: str) -> str:
    """Apply regex PII patterns to a free-form string."""
    for pattern in _PII_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    return s


def _pii_patcher(record: dict[str, Any]) -> None:
    """Loguru global patcher: masks known PII keys in structured extra fields.

    Also enriches record with tenant_id and user_id from contextvars when available.
    """
    extra = record["extra"]
    for key in list(extra.keys()):
        if key in _PII_KEYS:
            extra[key] = "[REDACTED]"

    if (tid := _log_tenant_id.get()) is not None:
        extra.setdefault("tenant_id", tid)
    if (uid := _log_user_id.get()) is not None:
        extra.setdefault("user_id", uid)


def _json_sink(message: Any) -> None:
    """Production JSON sink with PII-masked message text."""
    record = message.record
    output: dict[str, Any] = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "msg": _mask_string(record["message"]),
        **record["extra"],
    }
    print(json.dumps(output, default=str), file=sys.stdout, flush=True)


def configure_logging(app_env: str = "development") -> None:
    """Set up Loguru. Production: JSON to stdout with PII masking. Dev: colored human-readable."""
    logger.remove()
    logger.configure(patcher=_pii_patcher)

    if app_env == "production":
        logger.add(_json_sink, level="INFO")
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            level="DEBUG",
            colorize=True,
        )
```

- [ ] **Step 2: Verify import is clean**

```bash
cd backend && uv run python -c "from finacialsim_saas.middleware.logging import configure_logging, _log_tenant_id; print('OK')"
```

Expected: `OK`

---

### Task 4: Enrich context in auth deps

**Files:**
- Modify: `backend/finacialsim_saas/auth/deps.py`

- [ ] **Step 1: Set context vars after JWT decode**

Read `backend/finacialsim_saas/auth/deps.py` and find the `get_current_ctx` (or equivalent) function that extracts `tenant_id` and `user_id` from the JWT. After successfully parsing the JWT and constructing the `RequestContext`, add:

```python
    from finacialsim_saas.middleware.logging import _log_tenant_id, _log_user_id
    _log_tenant_id.set(str(ctx.tenant_id))
    _log_user_id.set(str(ctx.user_id))
```

This must go inside the dependency function body, after the `RequestContext` is constructed, before returning it. The exact insertion point depends on the function — read the file first to identify the right line.

- [ ] **Step 2: Verify no import errors**

```bash
cd backend && uv run python -c "from finacialsim_saas.auth.deps import get_current_ctx; print('OK')"
```

Expected: `OK`

---

### Task 5: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 2: Manual smoke — verify JSON logging in production mode**

```bash
cd backend && APP_ENV=production uv run python -c "
from finacialsim_saas.middleware.logging import configure_logging
from loguru import logger
configure_logging('production')
logger.bind(tenant_id='abc-123').info('test message user@example.com')
"
```

Expected: JSON line printed with `msg` containing `[REDACTED]` instead of the email address.

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/api/health.py \
        backend/finacialsim_saas/middleware/logging.py \
        backend/finacialsim_saas/auth/deps.py \
        backend/tests/test_health.py
git commit -m "feat(phase7d): extend /healthz with Redis check, add JSON logging with PII masking"
```
