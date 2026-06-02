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
    """ARQ cron: daily 11:00 UTC (= BRT 08:00). Enqueues due-soon reminders idempotently."""
    session_factory = ctx["session_factory"]
    target_date = date.today() + timedelta(days=3)

    async with session_factory() as session:
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
