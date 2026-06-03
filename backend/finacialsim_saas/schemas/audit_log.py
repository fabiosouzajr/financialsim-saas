import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    timestamp: datetime
    usuario_id: uuid.UUID | None
    usuario_email: str | None = None
    acao: str
    entidade: str | None
    entidade_id: uuid.UUID | None
    diff_json: dict | None

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    next_cursor: str | None
