from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class ClientIn(BaseModel):
    nome: str
    cpf_cnpj: str
    tipo: str  # "pf" | "pj"
    rg: str | None = None
    data_nasc: date | None = None
    profissao: str | None = None
    renda: DecimalStr | None = None
    telefone: str | None = None
    email: str | None = None
    endereco_json: dict | None = None
    observacoes: str | None = None


class ClientOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    nome: str
    cpf_cnpj: str
    tipo: str
    rg: str | None
    data_nasc: date | None
    profissao: str | None
    renda: DecimalStr | None
    telefone: str | None
    email: str | None
    endereco_json: dict | None
    observacoes: str | None
    is_active: bool
    criado_por: uuid.UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


class ClientListItem(BaseModel):
    id: uuid.UUID
    nome: str
    cpf_cnpj: str
    tipo: str
    telefone: str | None
    email: str | None
    is_active: bool
    criado_em: datetime

    class Config:
        from_attributes = True


class ClientListPage(BaseModel):
    items: list[ClientListItem]
    next_cursor: str | None
