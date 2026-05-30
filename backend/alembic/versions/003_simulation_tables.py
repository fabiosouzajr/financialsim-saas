"""simulation tables — business_rules, simulation_counters, simulations, fees, extras, rows, extraordinary

Revision ID: 003
Revises: 002
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE simulation_status AS ENUM ('rascunho', 'confirmado', 'arquivado')"
    )

    op.create_table(
        "business_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("chave", sa.Text, nullable=False),
        sa.Column("valor_json", JSONB, nullable=False),
        sa.Column("descricao", sa.Text, nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_por", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_business_rules_tenant", "business_rules", ["tenant_id"])
    op.create_unique_constraint(
        "uq_business_rules_tenant_chave", "business_rules", ["tenant_id", "chave"]
    )

    op.create_table(
        "simulation_counters",
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("next_val", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("tenant_id", "year"),
    )

    op.create_table(
        "simulations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("codigo", sa.Text, nullable=False),
        sa.Column("cliente_nome", sa.Text, nullable=True),
        sa.Column("veiculo_descricao", sa.Text, nullable=True),
        sa.Column("valor_veiculo", NUMERIC(18, 2), nullable=False),
        sa.Column("valor_entrada", NUMERIC(18, 2), nullable=False),
        sa.Column("valor_financiado", NUMERIC(18, 2), nullable=False),
        sa.Column("taxa_mensal", NUMERIC(10, 6), nullable=False),
        sa.Column("prazo_meses", sa.Integer, nullable=False),
        sa.Column("data_liberacao", sa.Date, nullable=False),
        sa.Column("primeiro_vencimento", sa.Date, nullable=False),
        sa.Column("incluir_iof", sa.Boolean, nullable=False),
        sa.Column("iof_total", NUMERIC(18, 2), nullable=False),
        sa.Column("parcela_financiamento", NUMERIC(18, 2), nullable=False),
        sa.Column("total_pago", NUMERIC(18, 2), nullable=False),
        sa.Column("total_juros", NUMERIC(18, 2), nullable=False),
        sa.Column("cet_mensal", NUMERIC(10, 6), nullable=False),
        sa.Column("cet_anual", NUMERIC(10, 6), nullable=False),
        sa.Column("status", sa.Enum(name="simulation_status", create_type=False),
                  nullable=False, server_default="confirmado"),
        sa.Column("rules_snapshot_json", JSONB, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=True, unique=True),
        sa.Column("criado_por", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_simulations_tenant", "simulations", ["tenant_id"])
    op.create_index("ix_simulations_tenant_criado_em",
                    "simulations", ["tenant_id", "criado_em"])
    op.create_unique_constraint(
        "uq_simulations_tenant_codigo", "simulations", ["tenant_id", "codigo"]
    )

    op.create_table(
        "simulation_fees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("valor", NUMERIC(18, 2), nullable=False),
        sa.Column("incluir_no_principal", sa.Boolean, nullable=False),
    )
    op.create_index("ix_simulation_fees_sim", "simulation_fees", ["simulation_id"])

    op.create_table(
        "simulation_extras",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("valor_total", NUMERIC(18, 2), nullable=False),
        sa.Column("modalidade", sa.Text, nullable=False),
        sa.Column("duracao_meses", sa.Integer, nullable=False),
        sa.Column("valor_por_parcela", NUMERIC(18, 2), nullable=False),
        sa.Column("ordem", sa.Integer, nullable=False),
    )
    op.create_index("ix_simulation_extras_sim", "simulation_extras", ["simulation_id"])

    op.create_table(
        "amortization_rows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("numero_parcela", sa.Integer, nullable=False),
        sa.Column("data_vencimento", sa.Date, nullable=False),
        sa.Column("dias_periodo", sa.Integer, nullable=False),
        sa.Column("saldo_anterior", NUMERIC(18, 2), nullable=False),
        sa.Column("juros", NUMERIC(18, 2), nullable=False),
        sa.Column("amortizacao", NUMERIC(18, 2), nullable=False),
        sa.Column("parcela", NUMERIC(18, 2), nullable=False),
        sa.Column("saldo_devedor", NUMERIC(18, 2), nullable=False),
        sa.Column("extras_total", NUMERIC(18, 2), nullable=False),
        sa.Column("parcela_total", NUMERIC(18, 2), nullable=False),
        sa.Column("ajuste_arredondamento", NUMERIC(18, 2), nullable=False),
    )
    op.create_index("ix_amortization_rows_sim_parcela",
                    "amortization_rows", ["simulation_id", "numero_parcela"])

    op.create_table(
        "extraordinary_amortizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("valor", NUMERIC(18, 2), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_extraordinary_sim", "extraordinary_amortizations", ["simulation_id"])


def downgrade() -> None:
    op.drop_table("extraordinary_amortizations")
    op.drop_table("amortization_rows")
    op.drop_table("simulation_extras")
    op.drop_table("simulation_fees")
    op.drop_table("simulations")
    op.drop_table("simulation_counters")
    op.drop_table("business_rules")
    op.execute("DROP TYPE simulation_status")
