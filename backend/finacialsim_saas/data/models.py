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
