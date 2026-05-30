"""cadastros — clients, vehicles, fipe_cache + FK columns on simulations

Revision ID: 004
Revises: 003
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE client_type AS ENUM ('pf', 'pj')")
    op.execute(
        "CREATE TYPE vehicle_status AS ENUM ('ativo', 'reservado', 'vendido', 'inativo')"
    )

    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("cpf_cnpj", sa.Text, nullable=False),
        sa.Column("tipo", sa.Enum("pf", "pj", name="client_type", create_type=False),
                  nullable=False),
        sa.Column("rg", sa.Text, nullable=True),
        sa.Column("data_nasc", sa.Date, nullable=True),
        sa.Column("profissao", sa.Text, nullable=True),
        sa.Column("renda", sa.Numeric(18, 2), nullable=True),
        sa.Column("telefone", sa.Text, nullable=True),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("endereco_json", JSONB, nullable=True),
        sa.Column("observacoes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("criado_por", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_clients_tenant", "clients", ["tenant_id"])
    op.create_unique_constraint(
        "uq_clients_tenant_cpf_cnpj", "clients", ["tenant_id", "cpf_cnpj"]
    )

    op.create_table(
        "vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("fonte", sa.Text, nullable=False),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("marca", sa.Text, nullable=False),
        sa.Column("modelo", sa.Text, nullable=False),
        sa.Column("ano_modelo", sa.Integer, nullable=False),
        sa.Column("combustivel", sa.Text, nullable=True),
        sa.Column("codigo_fipe", sa.Text, nullable=True),
        sa.Column("valor_fipe", sa.Numeric(18, 2), nullable=True),
        sa.Column("valor_referencia", sa.Numeric(18, 2), nullable=True),
        sa.Column("mes_referencia_fipe", sa.Text, nullable=True),
        sa.Column("cor", sa.Text, nullable=True),
        sa.Column("placa", sa.Text, nullable=True),
        sa.Column("odometro_km", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Enum("ativo", "reservado", "vendido", "inativo",
                    name="vehicle_status", create_type=False),
            nullable=False, server_default=sa.text("'ativo'"),
        ),
        sa.Column("snapshot_json", JSONB, nullable=True),
        sa.Column("criado_por", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_vehicles_tenant", "vehicles", ["tenant_id"])
    op.create_index("ix_vehicles_tenant_status", "vehicles", ["tenant_id", "status"])
    # Partial unique: only enforce unique placa within tenant when placa is not null
    op.execute(
        "CREATE UNIQUE INDEX uq_vehicles_tenant_placa "
        "ON vehicles(tenant_id, placa) WHERE placa IS NOT NULL"
    )

    op.create_table(
        "fipe_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("acao", sa.Text, nullable=False),
        sa.Column("marca_id", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("modelo_id", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("ano_id", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("ttl_horas", sa.Integer, nullable=False),
    )
    op.create_unique_constraint(
        "uq_fipe_cache_key", "fipe_cache",
        ["tipo", "acao", "marca_id", "modelo_id", "ano_id"]
    )

    # Nullable FKs on simulations — backward-compat with existing rows
    op.add_column(
        "simulations",
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id"), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("vehicle_id", UUID(as_uuid=True),
                  sa.ForeignKey("vehicles.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("simulations", "vehicle_id")
    op.drop_column("simulations", "client_id")
    op.drop_table("fipe_cache")
    op.drop_index("uq_vehicles_tenant_placa", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_table("clients")
    op.execute("DROP TYPE vehicle_status")
    op.execute("DROP TYPE client_type")
