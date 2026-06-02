from datetime import datetime, timezone
from pathlib import Path


class MaildirChannel:
    def __init__(self, maildir_path: str) -> None:
        self._path = Path(maildir_path)
        self._path.mkdir(parents=True, exist_ok=True)

    def deliver(self, *, to: str, subject: str, body: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        safe_to = to.replace("@", "_at_").replace("/", "_")
        filename = self._path / f"{ts}-{safe_to}.eml"
        filename.write_text(
            f"To: {to}\nSubject: {subject}\n\n{body}", encoding="utf-8"
        )


async def drain_outbox(ctx) -> None:  # noqa: ANN001 — ARQ context
    """ARQ task: reads pending notifications_outbox rows, writes to MaildirChannel."""
    from datetime import timezone
    from sqlalchemy import select

    from finacialsim_saas.data.database import build_session_factory
    from finacialsim_saas.data.models import NotificationsOutbox
    from finacialsim_saas.settings import get_settings

    settings = get_settings()
    channel = MaildirChannel(settings.maildir_path)
    engine = ctx.get("engine")
    factory = build_session_factory(engine)

    async with factory() as session:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(NotificationsOutbox).where(
                NotificationsOutbox.sent_at.is_(None),
                NotificationsOutbox.status == "pending",
            ).limit(50)
        )
        rows = result.scalars().all()

        for row in rows:
            try:
                _render_and_deliver(channel, row)
                row.sent_at = now
                row.status = "sent"
                row.updated_at = now
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)
                row.status = "failed"
                row.updated_at = now

        await session.commit()


def _render_and_deliver(channel: MaildirChannel, row) -> None:  # noqa: ANN001
    if row.template_key == "password_reset":
        subject = "Redefinição de senha — FinacialSim"
        body = (
            f"Olá {row.payload_json.get('user_name', '')},\n\n"
            f"Clique no link para redefinir sua senha:\n{row.payload_json['reset_url']}\n\n"
            "Link válido por 30 minutos."
        )
    elif row.template_key == "user_invite":
        subject = "Bem-vindo ao FinacialSim"
        body = (
            f"Olá {row.payload_json.get('user_name', '')},\n\n"
            "Sua conta foi criada. Use as credenciais fornecidas pelo administrador."
        )
    else:
        subject = f"Notificação: {row.template_key}"
        body = str(row.payload_json)
    channel.deliver(to=row.target_email or "", subject=subject, body=body)
