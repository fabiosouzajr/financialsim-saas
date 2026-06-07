# Phase 7C — Worker + Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `drain_notifications_outbox` (30s, Redis lock) and `schedule_parcela_due_reminders` (11:00 UTC) ARQ jobs. Wire all 6 trigger sites to `NotificationService.enqueue()`. Delete the obsolete `maildir.py` path.

**Architecture:** New `workers/notifications.py` holds both ARQ jobs. Registered in `WorkerSettings`. Each of the 6 trigger sites (auth/pix/parcela services) replaces its ad-hoc `NotificationsOutbox(...)` write with `NotificationService(session).enqueue(...)`. `maildir.py` and `test_maildir.py` are deleted.

**Tech Stack:** ARQ cron, aiosmtplib, SQLAlchemy async, Loguru, Redis

**Depends on:** Phase 7B (NotificationService, EmailChannel, templates, SMTP settings)

---

## File Map

| Action | File |
|--------|------|
| Create | `backend/finacialsim_saas/workers/notifications.py` |
| Modify | `backend/finacialsim_saas/workers/worker.py` — register drain + schedule jobs |
| Modify | `backend/finacialsim_saas/auth/service.py` — wire `auth.password_reset`, `portal.customer_invite` |
| Modify | `backend/finacialsim_saas/pix/service.py` — wire `portal.pix_link`, `portal.parcela_paid` |
| Modify | `backend/finacialsim_saas/services/parcela_service.py` — wire `portal.parcela_overdue` |
| Delete | `backend/finacialsim_saas/workers/maildir.py` |
| Delete | `backend/tests/test_maildir.py` |
| Create | `backend/tests/test_drain_outbox.py` |

---

### Task 1: Write failing drain tests

**Files:**
- Create: `backend/tests/test_drain_outbox.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for drain_notifications_outbox ARQ job (SMTP mocked)."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from finacialsim_saas.data.models import NotificationsOutbox
from finacialsim_saas.notifications.service import NotificationService

UTC = timezone.utc


@pytest.fixture
async def outbox_row(db_session):
    """Insert a pending outbox row and return it."""
    tenant_id = uuid.uuid4()
    svc = NotificationService(db_session)
    await svc.enqueue(
        template_key="auth.password_reset",
        payload={"reset_url": "https://example.com/reset/tok", "user_name": "Test"},
        target_email="recv@example.com",
        tenant_id=tenant_id,
    )
    await db_session.commit()
    result = await db_session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
    )
    return result.scalar_one()


async def _make_ctx(engine, session_factory):
    """Minimal ARQ ctx dict for drain job tests."""
    import redis.asyncio as aioredis
    from finacialsim_saas.settings import get_settings
    s = get_settings()
    redis = aioredis.from_url(str(s.redis_url), decode_responses=True)
    return {
        "engine": engine,
        "session_factory": session_factory,
        "redis": redis,
    }


async def test_drain_sends_pending_row(engine, session_factory):
    """A pending row gets sent and marked status=sent."""
    from finacialsim_saas.workers.notifications import drain_notifications_outbox

    tenant_id = uuid.uuid4()
    async with session_factory() as session:
        svc = NotificationService(session)
        await svc.enqueue(
            template_key="auth.password_reset",
            payload={"reset_url": "https://example.com/r/tok", "user_name": "Drain Test"},
            target_email="drain@example.com",
            tenant_id=tenant_id,
        )
        await session.commit()

    ctx = await _make_ctx(engine, session_factory)

    with patch(
        "finacialsim_saas.workers.notifications.EmailChannel.send",
        new_callable=AsyncMock,
    ) as mock_send:
        await drain_notifications_outbox(ctx)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "drain@example.com"
    assert "redefinição" in call_kwargs["subject"].lower() or "senha" in call_kwargs["subject"].lower()

    async with session_factory() as session:
        result = await session.execute(
            select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
        )
        row = result.scalar_one()
        assert row.status == "sent"
        assert row.sent_at is not None

    await ctx["redis"].aclose()


async def test_drain_retries_on_smtp_failure(engine, session_factory):
    """SMTP failure → status=pending, attempts++, scheduled_for pushed forward."""
    from finacialsim_saas.workers.notifications import drain_notifications_outbox

    tenant_id = uuid.uuid4()
    async with session_factory() as session:
        svc = NotificationService(session)
        await svc.enqueue(
            template_key="auth.password_reset",
            payload={"reset_url": "https://example.com/r/x", "user_name": "Retry Test"},
            target_email="retry@example.com",
            tenant_id=tenant_id,
        )
        await session.commit()

    ctx = await _make_ctx(engine, session_factory)

    with patch(
        "finacialsim_saas.workers.notifications.EmailChannel.send",
        new_callable=AsyncMock,
        side_effect=ConnectionRefusedError("SMTP down"),
    ):
        await drain_notifications_outbox(ctx)

    async with session_factory() as session:
        result = await session.execute(
            select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
        )
        row = result.scalar_one()
        assert row.status == "pending"
        assert row.attempts == 1
        assert row.last_error is not None
        assert row.scheduled_for > datetime.now(UTC)

    await ctx["redis"].aclose()


async def test_drain_deadletters_after_5_attempts(engine, session_factory):
    """After 5 failed attempts the row is deadlettered."""
    from finacialsim_saas.workers.notifications import drain_notifications_outbox

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as session:
        row = NotificationsOutbox(
            tenant_id=tenant_id,
            channel="email",
            template_key="auth.password_reset",
            payload_json={"reset_url": "x", "user_name": "y"},
            target_email="deadletter@example.com",
            scheduled_for=now,
            status="pending",
            attempts=4,  # one more failure → deadlettered
            updated_at=now,
            criado_em=now,
        )
        session.add(row)
        await session.commit()

    ctx = await _make_ctx(engine, session_factory)

    with patch(
        "finacialsim_saas.workers.notifications.EmailChannel.send",
        new_callable=AsyncMock,
        side_effect=ConnectionRefusedError("SMTP down"),
    ):
        await drain_notifications_outbox(ctx)

    async with session_factory() as session:
        result = await session.execute(
            select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
        )
        row = result.scalar_one()
        assert row.status == "deadlettered"
        assert row.attempts == 5

    await ctx["redis"].aclose()


async def test_drain_skips_non_email_channel(engine, session_factory):
    """Rows with channel != email are skipped with a warning, left pending."""
    from finacialsim_saas.workers.notifications import drain_notifications_outbox

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as session:
        row = NotificationsOutbox(
            tenant_id=tenant_id,
            channel="whatsapp",
            template_key="portal.parcela_paid",
            payload_json={"user_name": "x", "valor_pago": "R$ 100", "parcela_num": 1},
            target_email=None,
            target_phone="+5511999999999",
            scheduled_for=now,
            status="pending",
            attempts=0,
            updated_at=now,
            criado_em=now,
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    ctx = await _make_ctx(engine, session_factory)

    with patch(
        "finacialsim_saas.workers.notifications.EmailChannel.send",
        new_callable=AsyncMock,
    ) as mock_send:
        await drain_notifications_outbox(ctx)

    mock_send.assert_not_called()

    async with session_factory() as session:
        result = await session.execute(
            select(NotificationsOutbox).where(NotificationsOutbox.id == row_id)
        )
        row = result.scalar_one()
        assert row.status == "pending"

    await ctx["redis"].aclose()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_drain_outbox.py -v
```

Expected: FAIL — `drain_notifications_outbox` doesn't exist yet.

---

### Task 2: Create workers/notifications.py

**Files:**
- Create: `backend/finacialsim_saas/workers/notifications.py`

- [ ] **Step 1: Implement the drain job and schedule job**

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import or_, and_, select

from finacialsim_saas.data.models import (
    NotificationsOutbox, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, Role, Simulation, User,
)
from finacialsim_saas.notifications.channel import EmailChannel
from finacialsim_saas.notifications.service import NotificationService, render_template
from finacialsim_saas.settings import get_settings

UTC = timezone.utc
_LOCK_TTL = 25  # seconds — less than the 30s cron interval
_STUCK_THRESHOLD_SECS = 60


async def drain_notifications_outbox(ctx: dict) -> None:
    """ARQ job: runs every 30 s. Drains pending outbox rows via EmailChannel."""
    redis = ctx["redis"]
    acquired = await redis.set("lock:drain_notifications_outbox", "1", nx=True, ex=_LOCK_TTL)
    if not acquired:
        logger.debug("drain_notifications_outbox: already running, skipping")
        return

    settings = get_settings()
    channel = EmailChannel(settings)
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        now = datetime.now(UTC)
        stuck_threshold = now - timedelta(seconds=_STUCK_THRESHOLD_SECS)

        result = await session.execute(
            select(NotificationsOutbox)
            .where(
                or_(
                    and_(
                        NotificationsOutbox.status == "pending",
                        NotificationsOutbox.scheduled_for <= now,
                        NotificationsOutbox.attempts < 5,
                    ),
                    and_(
                        NotificationsOutbox.status == "sending",
                        NotificationsOutbox.updated_at <= stuck_threshold,
                    ),
                )
            )
            .limit(50)
        )
        rows = result.scalars().all()

        for row in rows:
            if row.channel != "email":
                logger.warning(
                    "drain_notifications_outbox: unsupported channel, leaving pending",
                    outbox_id=str(row.id),
                    channel=row.channel,
                )
                continue

            # Mark as sending to prevent concurrent drain picking the same row
            row.status = "sending"
            row.updated_at = datetime.now(UTC)
            await session.flush()

            try:
                subject, body_html, body_txt = render_template(
                    row.template_key, row.payload_json
                )
                await channel.send(
                    to=row.target_email,
                    subject=subject,
                    body_html=body_html,
                    body_txt=body_txt,
                )
                row.status = "sent"
                row.sent_at = datetime.now(UTC)
                row.updated_at = row.sent_at
                logger.info(
                    "drain_notifications_outbox: sent",
                    outbox_id=str(row.id),
                    template_key=row.template_key,
                )
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)[:500]
                row.updated_at = datetime.now(UTC)
                if row.attempts >= 5:
                    row.status = "deadlettered"
                    logger.error(
                        "drain_notifications_outbox: deadlettered after 5 attempts",
                        outbox_id=str(row.id),
                        template_key=row.template_key,
                        last_error=row.last_error,
                    )
                else:
                    row.status = "pending"
                    backoff_minutes = min(2 ** row.attempts, 60)
                    row.scheduled_for = datetime.now(UTC) + timedelta(minutes=backoff_minutes)
                    logger.warning(
                        "drain_notifications_outbox: smtp failure, will retry",
                        outbox_id=str(row.id),
                        template_key=row.template_key,
                        attempts=row.attempts,
                        backoff_minutes=backoff_minutes,
                    )

        await session.commit()


async def schedule_parcela_due_reminders(ctx: dict) -> None:
    """ARQ cron: daily 11:00 UTC (08:00 BRT). Enqueues due-soon reminders idempotently."""
    session_factory = ctx["session_factory"]
    target_date = date.today() + timedelta(days=3)

    async with session_factory() as session:
        # Get open parcelas due in exactly 3 days
        parcelas_result = await session.execute(
            select(ParcelaPayment)
            .join(Proposal, ParcelaPayment.proposal_id == Proposal.id)
            .where(
                ParcelaPayment.vencimento == target_date,
                ParcelaPayment.status == ParcelaPaymentStatus.open,
            )
        )
        parcelas = parcelas_result.scalars().all()

        svc = NotificationService(session)
        enqueued = 0

        for parcela in parcelas:
            proposal = await session.get(Proposal, parcela.proposal_id)
            if proposal is None:
                continue
            sim = await session.get(Simulation, proposal.simulation_id)
            if sim is None or sim.client_id is None:
                continue

            customer_result = await session.execute(
                select(User).where(
                    User.client_id == sim.client_id,
                    User.role == Role.customer,
                    User.is_active.is_(True),
                )
            )
            customer = customer_result.scalar_one_or_none()
            if customer is None or not customer.email or "@" not in customer.email:
                continue

            idem_key = f"portal.parcela_due_soon:{parcela.id}:{target_date.isoformat()}"
            await svc.enqueue(
                template_key="portal.parcela_due_soon",
                payload={
                    "user_name": customer.name,
                    "parcela_num": parcela.parcela_num,
                    "valor_parcela": str(parcela.valor_parcela),
                    "vencimento": target_date.isoformat(),
                    "proposal_id": str(proposal.id),
                },
                target_email=customer.email,
                tenant_id=parcela.tenant_id,
                idempotency_key=idem_key,
            )
            enqueued += 1

        await session.commit()
        logger.info(
            "schedule_parcela_due_reminders: done",
            enqueued=enqueued,
            target_date=target_date.isoformat(),
        )
```

- [ ] **Step 2: Run drain tests**

```bash
cd backend && uv run pytest tests/test_drain_outbox.py -v
```

Expected: All 4 tests pass.

---

### Task 3: Register jobs in WorkerSettings

**Files:**
- Modify: `backend/finacialsim_saas/workers/worker.py`

- [ ] **Step 1: Import and register the new jobs**

In `worker.py`, add the imports:

```python
from finacialsim_saas.workers.notifications import (
    drain_notifications_outbox,
    schedule_parcela_due_reminders,
)
```

Add to `WorkerSettings.functions`:

```python
    functions = [
        ping,
        func(render_proposta_pdf, timeout=120),
        func(render_carne_pdf, timeout=120),
        drain_notifications_outbox,  # also registered as cron — listed here for manual enqueue
    ]
```

Add to `WorkerSettings.cron_jobs` (after existing entries):

```python
        cron(drain_notifications_outbox, second={0, 30}),          # every 30 s
        cron(schedule_parcela_due_reminders, hour=11, minute=0),   # 08:00 BRT = 11:00 UTC
```

- [ ] **Step 2: Verify worker settings import cleanly**

```bash
cd backend && uv run python -c "from finacialsim_saas.workers.worker import WorkerSettings; print('OK')"
```

Expected: `OK`

---

### Task 4: Wire trigger sites (atomic swap)

**Files:**
- Modify: `backend/finacialsim_saas/auth/service.py`
- Modify: `backend/finacialsim_saas/pix/service.py`
- Modify: `backend/finacialsim_saas/services/parcela_service.py`

#### 4a — auth/service.py: password_reset

- [ ] **Step 1: Replace outbox write in `request_password_reset`**

Find the block starting at line ~183 in `backend/finacialsim_saas/auth/service.py`:

```python
        reset_url = f"{self._cfg.frontend_base_url}/reset-password/{raw}"
        self._s.add(
            NotificationsOutbox(
                tenant_id=user.tenant_id,
                type="password_reset",
                recipient=user.email,
                payload={"reset_url": reset_url, "user_name": user.name},
            )
        )
```

Replace with:

```python
        reset_url = f"{self._cfg.frontend_base_url}/reset-password/{raw}"
        from finacialsim_saas.notifications.service import NotificationService
        await NotificationService(self._s).enqueue(
            template_key="auth.password_reset",
            payload={"reset_url": reset_url, "user_name": user.name},
            target_email=user.email,
            tenant_id=user.tenant_id,
        )
```

#### 4b — auth/service.py: customer_invite

- [ ] **Step 2: Replace outbox write in `invite_customer`**

Find the block around line ~268 in `auth/service.py`:

```python
        # Write outbox
        payload: dict = {"user_id": str(user.id)}
        if proposal_id is not None:
            payload["proposal_id"] = str(proposal_id)
        self._s.add(
            NotificationsOutbox(
                tenant_id=ctx.tenant_id,
                type="customer_invite",
                recipient=user.email,
                payload=payload,
            )
        )
```

Replace with:

```python
        from finacialsim_saas.notifications.service import NotificationService
        invite_payload: dict = {
            "user_name": user.name,
            "portal_url": f"{self._cfg.frontend_base_url}/portal/login",
            "tenant_name": ctx.tenant_id,  # tenant name not available here; use ID as fallback
        }
        if proposal_id is not None:
            invite_payload["proposal_id"] = str(proposal_id)
        await NotificationService(self._s).enqueue(
            template_key="portal.customer_invite",
            payload=invite_payload,
            target_email=user.email,
            tenant_id=ctx.tenant_id,
        )
```

- [ ] **Step 3: Remove now-unused `NotificationsOutbox` import from auth/service.py**

In the imports at the top of `auth/service.py`, remove `NotificationsOutbox` from the import list:

```python
from finacialsim_saas.data.models import (
    AuditLog, PasswordResetToken,
    RefreshToken, Role, User,
)
```

#### 4c — pix/service.py: pix_link (after charge created)

- [ ] **Step 4: Add pix_link notification in `create_charge_for_parcela`**

In `backend/finacialsim_saas/pix/service.py`, at the end of `create_charge_for_parcela`, just before `return charge, qr_url` (after `await self._s.commit()`), add:

```python
        # Notify customer: Pix link available
        try:
            from finacialsim_saas.data.models import Simulation, User, Role
            from finacialsim_saas.notifications.service import NotificationService
            proposal = await self._s.get(Proposal, parcela.proposal_id)
            if proposal is not None:
                sim = await self._s.get(Simulation, proposal.simulation_id)
                if sim is not None and sim.client_id is not None:
                    from sqlalchemy import select
                    cu_result = await self._s.execute(
                        select(User).where(
                            User.client_id == sim.client_id,
                            User.role == Role.customer,
                            User.is_active.is_(True),
                        )
                    )
                    customer = cu_result.scalar_one_or_none()
                    if customer and "@" in (customer.email or ""):
                        portal_url = qr_url  # direct link to the charge view
                        await NotificationService(self._s).enqueue(
                            template_key="portal.pix_link",
                            payload={
                                "user_name": customer.name,
                                "valor_parcela": str(parcela.valor_parcela),
                                "parcela_num": parcela.parcela_num,
                                "pix_url": portal_url,
                            },
                            target_email=customer.email,
                            tenant_id=ctx.tenant_id,
                        )
                        await self._s.commit()
        except Exception as exc:
            # Notification failure must not break the charge creation flow
            logger.warning("pix_link notification failed", exc=str(exc))
```

Note: The `logger` import is needed here. Add it to `pix/service.py` if not present:
```python
from loguru import logger
```

#### 4d — pix/service.py: parcela_paid (in handle_webhook)

- [ ] **Step 5: Add parcela_paid notification in `handle_webhook`**

In `handle_webhook`, find the block that sets `parcela.status = ParcelaPaymentStatus.paid` (look for `PixChargeStatus.paid` processing). After the `await self._s.commit()` call for the paid event, add:

```python
            # Notify customer: payment confirmed
            try:
                from finacialsim_saas.data.models import Simulation, User, Role
                from finacialsim_saas.notifications.service import NotificationService
                if parcela_payment is not None:
                    proposal = await self._s.get(Proposal, parcela_payment.proposal_id)
                    if proposal is not None:
                        sim = await self._s.get(Simulation, proposal.simulation_id)
                        if sim is not None and sim.client_id is not None:
                            from sqlalchemy import select
                            cu_result = await self._s.execute(
                                select(User).where(
                                    User.client_id == sim.client_id,
                                    User.role == Role.customer,
                                )
                            )
                            customer = cu_result.scalar_one_or_none()
                            if customer and "@" in (customer.email or ""):
                                await NotificationService(self._s).enqueue(
                                    template_key="portal.parcela_paid",
                                    payload={
                                        "user_name": customer.name,
                                        "valor_pago": str(parcela_payment.paid_amount or parcela_payment.valor_parcela),
                                        "parcela_num": parcela_payment.parcela_num,
                                    },
                                    target_email=customer.email,
                                    tenant_id=parcela_payment.tenant_id,
                                    idempotency_key=f"portal.parcela_paid:{parcela_payment.id}",
                                )
                                await self._s.commit()
            except Exception as exc:
                logger.warning("parcela_paid notification failed", exc=str(exc))
```

To wire this correctly you need to read `handle_webhook` fully to find the exact paid-event processing block and the variable holding the `ParcelaPayment` row. The variable is likely `parcela_payment` — confirm by reading `pix/service.py` lines 150+.

#### 4e — parcela_service.py: parcela_overdue

- [ ] **Step 6: Replace outbox write in `mark_overdue`**

In `backend/finacialsim_saas/services/parcela_service.py`, find the block around line 188:

```python
            self._s.add(
                NotificationsOutbox(
                    tenant_id=parcela.tenant_id,
                    type="parcela_overdue",
                    recipient="",
                    payload={
                        "parcela_id": str(parcela.id),
                        "proposal_id": str(parcela.proposal_id),
                    },
                )
            )
```

Replace with:

```python
            try:
                from finacialsim_saas.data.models import Proposal, Simulation, User, Role
                from finacialsim_saas.notifications.service import NotificationService
                from sqlalchemy import select
                proposal = await self._s.get(Proposal, parcela.proposal_id)
                if proposal is not None:
                    sim = await self._s.get(Simulation, proposal.simulation_id)
                    if sim is not None and sim.client_id is not None:
                        cu_result = await self._s.execute(
                            select(User).where(
                                User.client_id == sim.client_id,
                                User.role == Role.customer,
                                User.is_active.is_(True),
                            )
                        )
                        customer = cu_result.scalar_one_or_none()
                        if customer and "@" in (customer.email or ""):
                            from datetime import date
                            dias_atraso = (date.today() - parcela.vencimento).days
                            await NotificationService(self._s).enqueue(
                                template_key="portal.parcela_overdue",
                                payload={
                                    "user_name": customer.name,
                                    "valor_parcela": str(parcela.valor_parcela),
                                    "parcela_num": parcela.parcela_num,
                                    "dias_atraso": max(dias_atraso, 1),
                                },
                                target_email=customer.email,
                                tenant_id=parcela.tenant_id,
                                idempotency_key=f"portal.parcela_overdue:{parcela.id}:{date.today().isoformat()}",
                            )
            except Exception as exc:
                from loguru import logger
                logger.warning("parcela_overdue notification failed", exc=str(exc))
```

- [ ] **Step 7: Remove now-unused `NotificationsOutbox` import from parcela_service.py**

In `parcela_service.py`, remove `NotificationsOutbox` from the models import.

---

### Task 5: Delete maildir

**Files:**
- Delete: `backend/finacialsim_saas/workers/maildir.py`
- Delete: `backend/tests/test_maildir.py`
- Modify: `backend/finacialsim_saas/settings.py` — remove `maildir_path`

- [ ] **Step 1: Delete files**

```bash
rm backend/finacialsim_saas/workers/maildir.py
rm backend/tests/test_maildir.py
```

- [ ] **Step 2: Remove `maildir_path` from Settings**

In `backend/finacialsim_saas/settings.py`, remove the line:

```python
    maildir_path: str = "./dev-mail"
```

- [ ] **Step 3: Verify no remaining references**

```bash
grep -r "maildir" backend/ --include="*.py"
```

Expected: No output.

---

### Task 6: Run full test suite

- [ ] **Step 1: Run tests**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All tests pass. `test_drain_outbox.py` all green.

- [ ] **Step 2: Commit**

```bash
git add backend/finacialsim_saas/workers/notifications.py \
        backend/finacialsim_saas/workers/worker.py \
        backend/finacialsim_saas/auth/service.py \
        backend/finacialsim_saas/pix/service.py \
        backend/finacialsim_saas/services/parcela_service.py \
        backend/finacialsim_saas/settings.py \
        backend/tests/test_drain_outbox.py
git rm backend/finacialsim_saas/workers/maildir.py backend/tests/test_maildir.py
git commit -m "feat(phase7c): add drain/schedule ARQ jobs, wire 6 trigger sites, delete maildir"
```
