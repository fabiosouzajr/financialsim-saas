from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class FeeIn(BaseModel):
    nome: str
    valor: DecimalStr
    incluir_no_principal: bool


class ExtraIn(BaseModel):
    tipo: str
    nome: str
    valor_total: DecimalStr
    modalidade: str  # mensal_continuo | rateio_meses | unico_inicial
    duracao_meses: int
    ordem: int


class SimulationCreate(BaseModel):
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
    valor_veiculo: DecimalStr
    valor_entrada: DecimalStr
    taxa_mensal: DecimalStr
    prazo_meses: int
    data_liberacao: date
    primeiro_vencimento: date
    incluir_iof: bool = True
    fees: list[FeeIn] = []
    extras: list[ExtraIn] = []
    idempotency_key: str | None = None


class SimulationPreviewRequest(BaseModel):
    valor_veiculo: DecimalStr
    valor_entrada: DecimalStr
    taxa_mensal: DecimalStr
    prazo_meses: int
    data_liberacao: date
    primeiro_vencimento: date
    incluir_iof: bool = True
    fees: list[FeeIn] = []
    extras: list[ExtraIn] = []


class FeeOut(BaseModel):
    id: uuid.UUID
    nome: str
    valor: DecimalStr
    incluir_no_principal: bool


class ExtraOut(BaseModel):
    id: uuid.UUID
    tipo: str
    nome: str
    valor_total: DecimalStr
    modalidade: str
    duracao_meses: int
    valor_por_parcela: DecimalStr
    ordem: int


class AmortizationRowOut(BaseModel):
    numero_parcela: int
    data_vencimento: date
    dias_periodo: int
    saldo_anterior: DecimalStr
    juros: DecimalStr
    amortizacao: DecimalStr
    parcela: DecimalStr
    saldo_devedor: DecimalStr
    extras_total: DecimalStr
    parcela_total: DecimalStr
    ajuste_arredondamento: DecimalStr


class SimulationSummary(BaseModel):
    parcela_financiamento: DecimalStr
    parcela_total_primeiro_ano: DecimalStr
    parcela_total_apos_rateio: DecimalStr
    valor_financiado: DecimalStr
    total_pago: DecimalStr
    total_juros: DecimalStr
    pct_juros: DecimalStr
    cet_mensal: DecimalStr
    cet_anual: DecimalStr
    total_pago_pelo_cliente: DecimalStr
    iof_total: DecimalStr


class SimulationPreviewResponse(BaseModel):
    summary: SimulationSummary
    rows: list[AmortizationRowOut]


class SimulationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    codigo: str
    client_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    cliente_nome: str | None
    veiculo_descricao: str | None
    valor_veiculo: DecimalStr
    valor_entrada: DecimalStr
    valor_financiado: DecimalStr
    taxa_mensal: DecimalStr
    prazo_meses: int
    data_liberacao: date
    primeiro_vencimento: date
    incluir_iof: bool
    iof_total: DecimalStr
    parcela_financiamento: DecimalStr
    total_pago: DecimalStr
    total_juros: DecimalStr
    cet_mensal: DecimalStr
    cet_anual: DecimalStr
    status: str
    criado_por: uuid.UUID
    criado_em: datetime
    atualizado_em: datetime
    fees: list[FeeOut] = []
    extras: list[ExtraOut] = []
    rows: list[AmortizationRowOut] = []
    summary: SimulationSummary | None = None


class SimulationListItem(BaseModel):
    id: uuid.UUID
    codigo: str
    client_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    cliente_nome: str | None
    veiculo_descricao: str | None
    valor_veiculo: DecimalStr
    valor_financiado: DecimalStr
    prazo_meses: int
    taxa_mensal: DecimalStr
    status: str
    criado_em: datetime


class SimulationListPage(BaseModel):
    items: list[SimulationListItem]
    next_cursor: str | None


class ValidationIssueOut(BaseModel):
    field: str
    message: str
    level: str
