"""Proposal schemas: PropostaSnapshot (sealed) + API request/response models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from finacialsim_core.money import quantize_brl
from finacialsim_saas.data.models import (
    AmortizationRow, Client, ClientType, Simulation,
    SimulationExtra, SimulationFee, Tenant, User, Vehicle,
)


class LojaSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    endereco: str | None = None


class VendedorSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str


class ClienteSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    tipo: str
    cpf_cnpj: str
    telefone: str | None = None


class VeiculoSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marca: str
    modelo: str
    ano_modelo: int
    descricao: str
    placa: str | None = None
    codigo_fipe: str | None = None
    mes_referencia_fipe: str | None = None


class SimSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor_veiculo: str
    valor_entrada: str
    valor_financiado: str
    prazo_meses: int
    taxa_mensal: str
    taxa_anual: str
    incluir_iof: bool
    iof_total: str
    tarifas_total: str
    valor_parcela: str
    total_pago: str
    total_juros: str
    cet_mensal: str
    cet_anual: str
    extras_acumulado: str


class ExtraSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    modalidade: str
    valor_total: str
    duracao_meses: int
    valor_por_parcela: str


class CronogramaRowSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero: int
    venc: str
    juros: str
    amortizacao: str
    parcela: str
    extras: str
    parcela_total: str
    saldo: str


class PropostaSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loja: LojaSnap
    vendedor: VendedorSnap
    cliente: ClienteSnap | None = None
    veiculo: VeiculoSnap | None = None
    sim: SimSnap
    extras: list[ExtraSnap]
    cronograma: list[CronogramaRowSnap]


def _d(v: object) -> Decimal:
    return Decimal(str(v))


def build_snapshot(
    sim: Simulation,
    fees: list[SimulationFee],
    extras: list[SimulationExtra],
    rows: list[AmortizationRow],
    client: Client | None,
    vehicle: Vehicle | None,
    tenant: Tenant,
    user: User,
) -> PropostaSnapshot:
    tarifas_total = sum((_d(f.valor) for f in fees), Decimal("0.00"))
    extras_acumulado = sum((_d(r.extras_total) for r in rows), Decimal("0.00"))
    taxa_anual = (1 + _d(sim.taxa_mensal)) ** 12 - 1

    cliente_snap = None
    if client is not None:
        tipo = "PF" if client.tipo == ClientType.pf else "PJ"
        cliente_snap = ClienteSnap(
            nome=client.nome,
            tipo=tipo,
            cpf_cnpj=client.cpf_cnpj,
            telefone=client.telefone,
        )

    veiculo_snap = None
    if vehicle is not None:
        veiculo_snap = VeiculoSnap(
            marca=vehicle.marca,
            modelo=vehicle.modelo,
            ano_modelo=vehicle.ano_modelo,
            descricao=f"{vehicle.marca} {vehicle.modelo} ({vehicle.ano_modelo})",
            placa=vehicle.placa,
            codigo_fipe=vehicle.codigo_fipe,
            mes_referencia_fipe=vehicle.mes_referencia_fipe,
        )

    return PropostaSnapshot(
        loja=LojaSnap(nome=tenant.name),
        vendedor=VendedorSnap(nome=user.name),
        cliente=cliente_snap,
        veiculo=veiculo_snap,
        sim=SimSnap(
            valor_veiculo=str(sim.valor_veiculo),
            valor_entrada=str(sim.valor_entrada),
            valor_financiado=str(sim.valor_financiado),
            prazo_meses=sim.prazo_meses,
            taxa_mensal=str(sim.taxa_mensal),
            taxa_anual=str(quantize_brl(taxa_anual)),
            incluir_iof=sim.incluir_iof,
            iof_total=str(sim.iof_total),
            tarifas_total=str(quantize_brl(tarifas_total)),
            valor_parcela=str(sim.parcela_financiamento),
            total_pago=str(sim.total_pago),
            total_juros=str(sim.total_juros),
            cet_mensal=str(sim.cet_mensal),
            cet_anual=str(sim.cet_anual),
            extras_acumulado=str(quantize_brl(extras_acumulado)),
        ),
        extras=[
            ExtraSnap(
                nome=e.nome,
                modalidade=e.modalidade,
                valor_total=str(e.valor_total),
                duracao_meses=e.duracao_meses,
                valor_por_parcela=str(e.valor_por_parcela),
            )
            for e in extras
        ],
        cronograma=[
            CronogramaRowSnap(
                numero=r.numero_parcela,
                venc=r.data_vencimento.isoformat(),
                juros=str(r.juros),
                amortizacao=str(r.amortizacao),
                parcela=str(r.parcela),
                extras=str(r.extras_total),
                parcela_total=str(r.parcela_total),
                saldo=str(r.saldo_devedor),
            )
            for r in rows
        ],
    )


class ProposalCreate(BaseModel):
    simulation_id: uuid.UUID


class ProposalOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    simulation_id: uuid.UUID
    codigo: str
    gerado_por: uuid.UUID
    gerado_em: datetime
    validade_dias: int
    render_status: str
    render_error: str | None
    status: str
    pdf_key: str | None
    carne_key: str | None
    aprovado_por: uuid.UUID | None
    aprovado_em: datetime | None
    cancelado_por: uuid.UUID | None
    cancelado_em: datetime | None


class ProposalListItem(BaseModel):
    id: uuid.UUID
    codigo: str
    simulation_id: uuid.UUID
    render_status: str
    status: str
    gerado_em: datetime


class ProposalListPage(BaseModel):
    items: list[ProposalListItem]
    next_cursor: str | None
