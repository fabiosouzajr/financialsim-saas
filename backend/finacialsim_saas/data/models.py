import enum as _enum_module
import enum
import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from finacialsim_saas.data.database import Base


class Role(enum.Enum):
    admin = "admin"
    manager = "manager"
    user = "user"
    customer = "customer"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slug: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    role: Mapped[Role] = mapped_column(
        sa.Enum(Role, name="userrole", native_enum=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    tokens_revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        sa.Index(
            "uq_users_email_staff", "email",
            unique=True, postgresql_where=sa.text("role != 'customer'"),
        ),
        sa.Index(
            "uq_users_tenant_email_customer", "tenant_id", "email",
            unique=True, postgresql_where=sa.text("role = 'customer'"),
        ),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acao: Mapped[str] = mapped_column(sa.Text, nullable=False)
    entidade: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    diff_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    hostname: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_audit_log_tenant_timestamp", "tenant_id", "timestamp"),
        sa.Index("ix_audit_log_tenant_entidade", "tenant_id", "entidade", "entidade_id"),
    )


class NotificationsOutbox(Base):
    __tablename__ = "notifications_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    recipient: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )


class SimulationStatus(_enum_module.Enum):
    rascunho = "rascunho"
    confirmado = "confirmado"
    arquivado = "arquivado"


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    chave: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valor_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    descricao: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "chave", name="uq_business_rules_tenant_chave"),
    )


class SimulationCounter(Base):
    __tablename__ = "simulation_counters"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    next_val: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )

    __table_args__ = (sa.PrimaryKeyConstraint("tenant_id", "year"),)


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    codigo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cliente_nome: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    veiculo_descricao: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valor_veiculo: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    valor_entrada: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    valor_financiado: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    taxa_mensal: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    prazo_meses: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    data_liberacao: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    primeiro_vencimento: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    incluir_iof: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    iof_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    parcela_financiamento: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    total_pago: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    total_juros: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    cet_mensal: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    cet_anual: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    status: Mapped[SimulationStatus] = mapped_column(
        sa.Enum(SimulationStatus, name="simulation_status", native_enum=True),
        nullable=False, server_default="confirmado"
    )
    rules_snapshot_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True, unique=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=True
    )
    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.Index("ix_simulations_tenant_criado_em", "tenant_id", "criado_em"),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_simulations_tenant_codigo"),
    )


class SimulationFee(Base):
    __tablename__ = "simulation_fees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    nome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valor: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    incluir_no_principal: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)


class SimulationExtra(Base):
    __tablename__ = "simulation_extras"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tipo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    nome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    modalidade: Mapped[str] = mapped_column(sa.Text, nullable=False)
    duracao_meses: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    valor_por_parcela: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    ordem: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class AmortizationRow(Base):
    __tablename__ = "amortization_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    numero_parcela: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    data_vencimento: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    dias_periodo: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    saldo_anterior: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    juros: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    amortizacao: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    parcela: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    saldo_devedor: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    extras_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    parcela_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    ajuste_arredondamento: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)

    __table_args__ = (
        sa.Index("ix_amortization_rows_sim_parcela", "simulation_id", "numero_parcela"),
    )


class ExtraordinaryAmortization(Base):
    __tablename__ = "extraordinary_amortizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    data: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


class ClientType(enum.Enum):
    pf = "pf"
    pj = "pj"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tipo: Mapped[ClientType] = mapped_column(
        sa.Enum(ClientType, name="client_type", native_enum=True), nullable=False
    )
    rg: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    data_nasc: Mapped[datetime | None] = mapped_column(sa.Date, nullable=True)
    profissao: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    renda: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    telefone: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    endereco_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "cpf_cnpj", name="uq_clients_tenant_cpf_cnpj"),
    )


class VehicleStatus(enum.Enum):
    ativo = "ativo"
    reservado = "reservado"
    vendido = "vendido"
    inativo = "inativo"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    fonte: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tipo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    marca: Mapped[str] = mapped_column(sa.Text, nullable=False)
    modelo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    ano_modelo: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    combustivel: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    codigo_fipe: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valor_fipe: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    valor_referencia: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    mes_referencia_fipe: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cor: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    placa: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    odometro_km: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    status: Mapped[VehicleStatus] = mapped_column(
        sa.Enum(VehicleStatus, name="vehicle_status", native_enum=True),
        nullable=False, server_default=sa.text("'ativo'"),
    )
    snapshot_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.Index("ix_vehicles_tenant_status", "tenant_id", "status"),
    )


class FipeCache(Base):
    __tablename__ = "fipe_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tipo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    acao: Mapped[str] = mapped_column(sa.Text, nullable=False)
    marca_id: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    modelo_id: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    ano_id: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    payload_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    ttl_horas: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "tipo", "acao", "marca_id", "modelo_id", "ano_id",
            name="uq_fipe_cache_key",
        ),
    )


class IndicatorHistory(Base):
    __tablename__ = "indicators_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    data_referencia: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    unidade: Mapped[str] = mapped_column(sa.Text, nullable=False)
    fonte: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    coletado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "codigo", "data_referencia", name="uq_indicators_history_codigo_date"
        ),
    )


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    provider_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    success: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_provider_health_name_checked", "provider_name", "checked_at"),
    )


class ProposalRenderStatus(enum.Enum):
    pending = "pending"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


class ProposalStatus(enum.Enum):
    rascunho = "rascunho"
    ready = "ready"
    aprovada = "aprovada"
    cancelada = "cancelada"


class ParcelaPaymentStatus(enum.Enum):
    pending = "pending"
    paid = "paid"
    canceled = "canceled"


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("simulations.id"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    gerado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    gerado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    validade_dias: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("7")
    )
    snapshot_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    pdf_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    carne_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    render_status: Mapped[ProposalRenderStatus] = mapped_column(
        sa.Enum(ProposalRenderStatus, name="proposal_render_status", native_enum=True),
        nullable=False, server_default=sa.text("'pending'"),
    )
    render_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(
        sa.Enum(ProposalStatus, name="proposal_status", native_enum=True),
        nullable=False, server_default=sa.text("'rascunho'"),
    )
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aprovado_em: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    cancelado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_proposals_tenant_codigo"),
        sa.UniqueConstraint("tenant_id", "simulation_id", name="uq_proposals_tenant_simulation"),
        sa.Index("ix_proposals_tenant_gerado_em", "tenant_id", "gerado_em"),
    )


class ParcelaPayment(Base):
    __tablename__ = "parcela_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    parcela_num: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    vencimento: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    valor_parcela: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    status: Mapped[ParcelaPaymentStatus] = mapped_column(
        sa.Enum(ParcelaPaymentStatus, name="parcela_payment_status", native_enum=True),
        nullable=False, server_default=sa.text("'pending'"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    pix_charge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        sa.Index("ix_parcela_payments_proposal_num", "proposal_id", "parcela_num"),
    )
