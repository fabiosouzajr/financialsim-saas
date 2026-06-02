"""Tests for drain_notifications_outbox ARQ job (SMTP mocked)."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from finacialsim_saas.data.models import NotificationsOutbox
from finacialsim_saas.notifications.service import NotificationService

UTC = timezone.utc


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

    async with session_factory() as session:
        result = await session.execute(
            select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
        )
        row = result.scalar_one()
        assert row.status == "sent"
        assert row.sent_at is not None

    await ctx["redis"].aclose()


async def test_drain_retries_on_smtp_failure(engine, session_factory):
    """SMTP failure -> status=pending, attempts++, scheduled_for pushed forward."""
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
            attempts=4,  # one more failure -> deadlettered
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
    """Rows with channel != email are skipped, left pending."""
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


async def test_drain_recovers_stuck_sending_row(engine, session_factory):
    """A row stuck in 'sending' for > 60s is re-processed."""
    from finacialsim_saas.workers.notifications import drain_notifications_outbox

    tenant_id = uuid.uuid4()
    now = datetime.now(UTC)
    stuck_since = now - timedelta(seconds=65)

    async with session_factory() as session:
        row = NotificationsOutbox(
            tenant_id=tenant_id,
            channel="email",
            template_key="auth.password_reset",
            payload_json={"reset_url": "https://example.com/r/stuck", "user_name": "Stuck"},
            target_email="stuck@example.com",
            scheduled_for=stuck_since,
            status="sending",  # stuck — worker crashed mid-send
            attempts=1,
            updated_at=stuck_since,
            criado_em=stuck_since,
        )
        session.add(row)
        await session.commit()

    ctx = await _make_ctx(engine, session_factory)

    with patch(
        "finacialsim_saas.workers.notifications.EmailChannel.send",
        new_callable=AsyncMock,
    ) as mock_send:
        await drain_notifications_outbox(ctx)

    mock_send.assert_called_once()

    async with session_factory() as session:
        result = await session.execute(
            select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
        )
        row = result.scalar_one()
        assert row.status == "sent"

    await ctx["redis"].aclose()
