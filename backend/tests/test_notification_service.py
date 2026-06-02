"""Integration tests for NotificationService.enqueue() — DB only, no SMTP."""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from finacialsim_saas.data.models import NotificationsOutbox
from finacialsim_saas.notifications.service import NotificationService


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


async def test_enqueue_writes_pending_row(session, tenant_id):
    svc = NotificationService(session)
    await svc.enqueue(
        template_key="auth.password_reset",
        payload={"reset_url": "https://example.com/reset/abc", "user_name": "Test"},
        target_email="test@example.com",
        tenant_id=tenant_id,
    )
    await session.flush()

    result = await session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.tenant_id == tenant_id)
    )
    row = result.scalar_one()
    assert row.status == "pending"
    assert row.template_key == "auth.password_reset"
    assert row.target_email == "test@example.com"
    assert row.channel == "email"
    assert row.attempts == 0
    assert row.payload_json["reset_url"] == "https://example.com/reset/abc"


async def test_enqueue_with_idempotency_key_deduplicates(session, tenant_id):
    svc = NotificationService(session)
    idem_key = f"test:{uuid.uuid4()}"

    await svc.enqueue(
        template_key="portal.parcela_due_soon",
        payload={"parcela_num": 1, "valor_parcela": "R$ 100,00", "vencimento": "2026-06-10", "user_name": "X"},
        target_email="user@example.com",
        tenant_id=tenant_id,
        idempotency_key=idem_key,
    )
    await session.flush()

    # Second call with same key — ON CONFLICT DO NOTHING
    await svc.enqueue(
        template_key="portal.parcela_due_soon",
        payload={"parcela_num": 1, "valor_parcela": "R$ 100,00", "vencimento": "2026-06-10", "user_name": "X"},
        target_email="user@example.com",
        tenant_id=tenant_id,
        idempotency_key=idem_key,
    )
    await session.flush()

    result = await session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.idempotency_key == idem_key)
    )
    rows = result.scalars().all()
    assert len(rows) == 1, "idempotency_key should deduplicate enqueue calls"


async def test_enqueue_scheduled_for_future(session, tenant_id):
    future = datetime.now(timezone.utc) + timedelta(hours=2)

    svc = NotificationService(session)
    await svc.enqueue(
        template_key="auth.password_reset",
        payload={"reset_url": "x", "user_name": "y"},
        target_email="future@example.com",
        tenant_id=tenant_id,
        scheduled_for=future,
    )
    await session.flush()

    result = await session.execute(
        select(NotificationsOutbox).where(NotificationsOutbox.target_email == "future@example.com")
    )
    row = result.scalar_one()
    assert row.scheduled_for.replace(tzinfo=timezone.utc) >= future - timedelta(seconds=1)
