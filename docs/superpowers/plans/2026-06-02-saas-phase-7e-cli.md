# Phase 7E — CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `db migrate`, `db reset --confirm`, `notifications retry --outbox-id <id>`, and `notifications drain` sub-commands to the `finacialsim-saas` CLI.

**Architecture:** Two new Typer sub-apps (`cli/db.py`, `cli/notifications_cli.py`) mounted in `cli/main.py` via `app.add_typer()`. `db migrate` calls Alembic Python API. `notifications drain` calls `drain_notifications_outbox` directly (not via ARQ). `notifications retry` fetches a specific row, resets it to `pending`, then drains.

**Tech Stack:** Typer, Alembic Python API, asyncio, ARQ context mock

**Depends on:** Phase 7B (NotificationService), Phase 7C (drain_notifications_outbox)

---

## File Map

| Action | File |
|--------|------|
| Create | `backend/finacialsim_saas/cli/db.py` |
| Create | `backend/finacialsim_saas/cli/notifications_cli.py` |
| Modify | `backend/finacialsim_saas/cli/main.py` — mount new sub-apps |
| Modify | `backend/tests/test_cli.py` — add tests for new commands |

---

### Task 1: Write failing CLI tests

**Files:**
- Modify: `backend/tests/test_cli.py`

- [ ] **Step 1: Add tests for db and notifications sub-commands**

Open `backend/tests/test_cli.py` and append:

```python
def test_db_migrate_runs_without_error(runner):
    from finacialsim_saas.cli.main import app
    # db migrate should run alembic upgrade head and print confirmation
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0, result.output
    assert "migrate" in result.output.lower() or "head" in result.output.lower()


def test_notifications_drain_runs_without_error(runner):
    from finacialsim_saas.cli.main import app
    # drain with no pending rows should complete cleanly
    result = runner.invoke(app, ["notifications", "drain"])
    assert result.exit_code == 0, result.output


def test_notifications_retry_unknown_id(runner):
    import uuid
    from finacialsim_saas.cli.main import app
    bad_id = str(uuid.uuid4())
    result = runner.invoke(app, ["notifications", "retry", "--outbox-id", bad_id])
    assert result.exit_code != 0 or "not found" in result.output.lower()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && uv run pytest tests/test_cli.py -v -k "test_db_migrate or test_notifications"
```

Expected: FAIL — sub-commands don't exist yet.

---

### Task 2: Create cli/db.py

**Files:**
- Create: `backend/finacialsim_saas/cli/db.py`

- [ ] **Step 1: Implement db sub-app**

```python
import asyncio
from pathlib import Path

import typer

db_app = typer.Typer(help="Database management commands")


def _alembic_config():
    from alembic.config import Config
    alembic_ini = Path(__file__).parent.parent.parent / "alembic.ini"
    if not alembic_ini.exists():
        # Construct config from env when alembic.ini is not present (Docker)
        from finacialsim_saas.settings import get_settings
        cfg = Config()
        cfg.set_main_option("script_location", str(Path(__file__).parent.parent.parent / "alembic"))
        cfg.set_main_option("sqlalchemy.url", str(get_settings().database_url).replace("+asyncpg", ""))
        return cfg
    cfg = Config(str(alembic_ini))
    return cfg


@db_app.command("migrate")
def db_migrate():
    """Run Alembic upgrade head."""
    from alembic import command as alembic_command
    cfg = _alembic_config()
    alembic_command.upgrade(cfg, "head")
    typer.echo("Database migrated to head.")


@db_app.command("reset")
def db_reset(
    confirm: bool = typer.Option(False, "--confirm", help="Required to actually reset"),
):
    """Drop all tables and re-run migrations. Dev only."""
    import os
    from finacialsim_saas.settings import get_settings

    settings = get_settings()
    if settings.app_env == "production":
        typer.echo("Error: db reset is not allowed in production.", err=True)
        raise typer.Exit(1)
    if not confirm:
        typer.echo("Error: pass --confirm to actually reset the database.", err=True)
        raise typer.Exit(1)

    async def _reset():
        from finacialsim_saas.data.database import build_engine
        from sqlalchemy import text
        engine = build_engine(str(settings.database_url))
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(_reset())

    from alembic import command as alembic_command
    alembic_command.upgrade(_alembic_config(), "head")
    typer.echo("Database reset and migrated to head.")
```

---

### Task 3: Create cli/notifications_cli.py

**Files:**
- Create: `backend/finacialsim_saas/cli/notifications_cli.py`

- [ ] **Step 1: Implement notifications sub-app**

```python
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
    outbox_id: Annotated[str, typer.Option("--outbox-id", help="UUID of the outbox row to retry")],
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

        redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
        ctx = {"engine": engine, "session_factory": factory, "redis": redis}
        await redis.delete("lock:drain_notifications_outbox")
        await drain_notifications_outbox(ctx)
        await redis.aclose()
        engine.dispose()
        typer.echo("Retry drain complete.")

    asyncio.run(_run())
```

---

### Task 4: Mount sub-apps in cli/main.py

**Files:**
- Modify: `backend/finacialsim_saas/cli/main.py`

- [ ] **Step 1: Add imports and mount sub-apps**

In `backend/finacialsim_saas/cli/main.py`, add after the existing `user_app` import/mount lines:

```python
from finacialsim_saas.cli.db import db_app
from finacialsim_saas.cli.notifications_cli import notifications_app

app.add_typer(db_app, name="db")
app.add_typer(notifications_app, name="notifications")
```

Place these lines directly after the existing `app.add_typer(user_app, name="user")` line.

- [ ] **Step 2: Verify CLI help**

```bash
cd backend && uv run finacialsim-saas --help
```

Expected: Output shows `db`, `notifications`, `tenant`, `user` as sub-commands.

```bash
cd backend && uv run finacialsim-saas db --help
cd backend && uv run finacialsim-saas notifications --help
```

Expected: Each shows its sub-commands.

---

### Task 5: Run tests and commit

- [ ] **Step 1: Run CLI tests**

```bash
cd backend && uv run pytest tests/test_cli.py -v
```

Expected: All CLI tests pass, including the 3 new ones.

- [ ] **Step 2: Run full suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/cli/db.py \
        backend/finacialsim_saas/cli/notifications_cli.py \
        backend/finacialsim_saas/cli/main.py \
        backend/tests/test_cli.py
git commit -m "feat(phase7e): add db migrate/reset and notifications retry/drain CLI sub-commands"
```
