from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False)  # vendedor|gerente|admin
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)  # noqa: E501
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(2), nullable=False)  # PF|PJ
    rg: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_nasc: Mapped[date | None] = mapped_column(Date, nullable=True)
    profissao: Mapped[str | None] = mapped_column(String(100), nullable=True)
    renda: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    endereco_json: Mapped[str | None] = mapped_column(String, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)  # noqa: E501


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte: Mapped[str] = mapped_column(String(40), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    marca: Mapped[str] = mapped_column(String(80), nullable=False)
    modelo: Mapped[str] = mapped_column(String(120), nullable=False)
    ano_modelo: Mapped[int] = mapped_column(Integer, nullable=False)
    combustivel: Mapped[str] = mapped_column(String(40), nullable=False)
    codigo_fipe: Mapped[str | None] = mapped_column(String(40), nullable=True)
    valor_fipe: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    valor_referencia: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    mes_referencia_fipe: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    placa: Mapped[str | None] = mapped_column(String(10), nullable=True)
    odometro_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="disponivel")  # disponivel|reservado|vendido
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class SimulationFee(Base):
    __tablename__ = "simulation_fees"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    incluir_no_principal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SimulationExtra(Base):
    __tablename__ = "simulation_extras"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    modalidade: Mapped[str] = mapped_column(String(30), nullable=False)
    duracao_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_por_parcela: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AmortizationRow(Base):
    __tablename__ = "amortization_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False, index=True)  # noqa: E501
    numero_parcela: Mapped[int] = mapped_column(Integer, nullable=False)
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    dias_periodo: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_anterior: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    juros: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amortizacao: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    parcela: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    saldo_devedor: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    extras_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)  # noqa: E501
    parcela_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)  # noqa: E501
    ajuste_arredondamento: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)  # noqa: E501


class ExtraordinaryAmortization(Base):
    __tablename__ = "extraordinary_amortizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    modo: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    aplicado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    veiculo_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    criado_por: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    valor_veiculo: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_entrada: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pct_entrada: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    prazo_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    taxa_juros_mes: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    taxa_juros_ano: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    data_liberacao: Mapped[date] = mapped_column(Date, nullable=False)
    data_primeiro_venc: Mapped[date] = mapped_column(Date, nullable=False)
    dias_carencia: Mapped[int] = mapped_column(Integer, nullable=False)
    incluir_iof: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    iof_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tarifas_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    extras_total_acumulado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_financiado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_parcela: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_pago: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_juros: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pct_juros: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    cet_mes: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    cet_ano: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rules_snapshot_json: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)  # noqa: E501

    fees: Mapped[list[SimulationFee]] = relationship(cascade="all, delete-orphan")
    extras: Mapped[list[SimulationExtra]] = relationship(cascade="all, delete-orphan")
    rows: Mapped[list[AmortizationRow]] = relationship(
        cascade="all, delete-orphan",
        order_by="AmortizationRow.numero_parcela",
    )


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    gerado_por: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(String, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    carne_path: Mapped[str | None] = mapped_column(String, nullable=True)
    validade_dias: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    gerado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_a_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    simulation_b_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"), nullable=False)
    criado_por: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class IndicatorHistory(Base):
    __tablename__ = "indicators_history"
    __table_args__ = (UniqueConstraint("codigo", "data_referencia", name="uq_indicator_codigo_data"),)  # noqa: E501

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    unidade: Mapped[str] = mapped_column(String(10), nullable=False)
    fonte: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(String, nullable=True)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    valor_json: Mapped[str] = mapped_column(String, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)  # noqa: E501
    atualizado_por: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acao: Mapped[str] = mapped_column(String(80), nullable=False)
    entidade: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff_json: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(120), nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor_json: Mapped[str] = mapped_column(String, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)  # noqa: E501


class FipeCache(Base):
    __tablename__ = "fipe_cache"
    __table_args__ = (
        UniqueConstraint("tipo", "acao", "marca_id", "modelo_id", "ano_id", name="uq_fipe_cache_query"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    acao: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    marca_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    modelo_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ano_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload_json: Mapped[str] = mapped_column(String, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    ttl_horas: Mapped[int] = mapped_column(Integer, default=720, nullable=False)
