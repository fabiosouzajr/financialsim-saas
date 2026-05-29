"""RulesService - typed access to business_rules."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.data.repositories import BusinessRuleRepository
from app.services.audit_service import AuditService


class RulesService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = BusinessRuleRepository(session)
        self.audit = AuditService(session)

    def get_raw(self, chave: str) -> str | None:
        return self.repo.get(chave)

    def get_decimal(self, chave: str, default: Decimal) -> Decimal:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return Decimal(raw)

    def get_int(self, chave: str, default: int) -> int:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return int(raw)

    def get_bool(self, chave: str, default: bool) -> bool:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return raw.lower() in {"true", "1", "yes"}

    def get_json(self, chave: str, default: Any) -> Any:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return json.loads(raw)

    def set(self, chave: str, value: Any, user_id: int | None = None) -> None:
        old = self.get_raw(chave)
        valor_json = json.dumps(value) if not isinstance(value, str) else value
        self.repo.set(chave, valor_json, user_id=user_id)
        self.audit.log(
            usuario_id=user_id, acao="config_alterada",
            entidade="business_rules",
            diff={"chave": chave, "old": old, "new": valor_json},
        )
