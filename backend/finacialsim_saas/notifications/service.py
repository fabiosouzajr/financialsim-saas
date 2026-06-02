from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import NotificationsOutbox

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def render_template(template_key: str, payload: dict[str, Any]) -> tuple[str, str, str]:
    """Render a template. Returns (subject, body_html, body_txt).

    template_key uses dots: "auth.password_reset" -> looks in templates/auth/password_reset/
    """
    key_path = template_key.replace(".", "/")
    env = _jinja_env()
    subject = env.get_template(f"{key_path}/subject.txt").render(**payload).strip()
    body_html = env.get_template(f"{key_path}/body.html").render(**payload)
    body_txt = env.get_template(f"{key_path}/body.txt").render(**payload)
    return subject, body_html, body_txt


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def enqueue(
        self,
        template_key: str,
        payload: dict[str, Any],
        target_email: str | None,
        *,
        tenant_id: uuid.UUID,
        channel: str = "email",
        target_phone: str | None = None,
        scheduled_for: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Write an outbox row in the caller's open transaction.

        If idempotency_key is provided, uses INSERT ... ON CONFLICT DO NOTHING
        so duplicate calls (e.g. cron re-run) are safe.
        """
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "tenant_id": tenant_id,
            "channel": channel,
            "template_key": template_key,
            "payload_json": payload,
            "target_email": target_email,
            "target_phone": target_phone,
            "scheduled_for": scheduled_for or now,
            "status": "pending",
            "attempts": 0,
            "idempotency_key": idempotency_key,
            "updated_at": now,
            "criado_em": now,
        }
        if idempotency_key is not None:
            stmt = (
                pg_insert(NotificationsOutbox)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            await self._s.execute(stmt)
        else:
            self._s.add(NotificationsOutbox(**values))
