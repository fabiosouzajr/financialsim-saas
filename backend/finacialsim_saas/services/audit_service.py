from __future__ import annotations

import uuid
from base64 import b64decode, b64encode
from datetime import date, datetime, time, timezone
from typing import Any
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import AuditLog, Role

UTC = timezone.utc
PAGE_SIZE = 20


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log(
        self,
        acao: str,
        entidade: str | None,
        entidade_id: uuid.UUID | None,
        diff: dict[str, Any] | None,
        ctx: RequestContext,
    ) -> None:
        self._s.add(
            AuditLog(
                tenant_id=ctx.tenant_id,
                usuario_id=ctx.user_id,
                acao=acao,
                entidade=entidade,
                entidade_id=entidade_id,
                diff_json=diff,
            )
        )

    async def list(
        self,
        tenant_id: uuid.UUID,
        caller_role: Role,
        caller_user_id: uuid.UUID,
        usuario_id: uuid.UUID | None = None,
        entidade: str | None = None,
        acao: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
    ) -> tuple[list[AuditLog], str | None]:
        q = select(AuditLog).where(AuditLog.tenant_id == tenant_id)

        if caller_role == Role.user:
            q = q.where(AuditLog.usuario_id == caller_user_id)
        elif usuario_id is not None:
            q = q.where(AuditLog.usuario_id == usuario_id)

        if entidade:
            q = q.where(AuditLog.entidade == entidade)
        if acao:
            q = q.where(AuditLog.acao == acao)
        if date_from:
            q = q.where(AuditLog.timestamp >= datetime.combine(date_from, time.min, UTC))
        if date_to:
            q = q.where(AuditLog.timestamp <= datetime.combine(date_to, time.max, UTC))
        if cursor:
            ts, uid = _decode_cursor(cursor)
            q = q.where(
                (AuditLog.timestamp < ts)
                | ((AuditLog.timestamp == ts) & (AuditLog.id < uid))
            )

        q = q.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(PAGE_SIZE + 1)
        rows = (await self._s.scalars(q)).all()

        has_more = len(rows) > PAGE_SIZE
        items = list(rows[:PAGE_SIZE])
        next_cursor = (
            _encode_cursor(items[-1].timestamp, items[-1].id) if has_more else None
        )
        return items, next_cursor


def _encode_cursor(ts: datetime, uid: uuid.UUID) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return b64encode(json.dumps({"ts": ts.isoformat(), "id": str(uid)}).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    data = json.loads(b64decode(cursor))
    return datetime.fromisoformat(data["ts"]), uuid.UUID(data["id"])
