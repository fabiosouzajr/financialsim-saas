from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class VehicleIn(BaseModel):
    fonte: str         # "fipe_parallelum" | "fipe_brasilapi" | "manual"
    tipo: str          # "carro" | "moto" | "caminhao"
    marca: str
    modelo: str
    ano_modelo: int
    combustivel: str | None = None
    codigo_fipe: str | None = None
    valor_fipe: DecimalStr | None = None
    valor_referencia: DecimalStr | None = None
    mes_referencia_fipe: str | None = None
    cor: str | None = None
    placa: str | None = None
    odometro_km: int | None = None
    snapshot_json: dict | None = None


class VehicleOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    fonte: str
    tipo: str
    marca: str
    modelo: str
    ano_modelo: int
    combustivel: str | None
    codigo_fipe: str | None
    valor_fipe: DecimalStr | None
    valor_referencia: DecimalStr | None
    mes_referencia_fipe: str | None
    cor: str | None
    placa: str | None
    odometro_km: int | None
    status: str
    snapshot_json: dict | None
    criado_por: uuid.UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


class VehicleListItem(BaseModel):
    id: uuid.UUID
    tipo: str
    marca: str
    modelo: str
    ano_modelo: int
    placa: str | None
    valor_fipe: DecimalStr | None
    status: str
    criado_em: datetime

    class Config:
        from_attributes = True


class VehicleListPage(BaseModel):
    items: list[VehicleListItem]
    next_cursor: str | None


class VehicleStatusUpdate(BaseModel):
    status: str
