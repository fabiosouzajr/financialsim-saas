"""AuditService - business-event log persisted to audit_log table."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.data.models import AuditLog


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log(
        self,
        acao: str,
        usuario_id: int | None = None,
        entidade: str | None = None,
        entidade_id: int | None = None,
        diff: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            timestamp=datetime.now(UTC).replace(tzinfo=None),
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            diff_json=json.dumps(diff) if diff is not None else None,
            ip=None,
            hostname=socket.gethostname(),
        )
        self.session.add(entry)
        self.session.commit()
        return entry
