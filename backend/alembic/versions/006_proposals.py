"""proposals and parcela_payments tables

Revision ID: 006
Revises: 005
Create Date: 2026-06-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE proposal_render_status AS ENUM "
        "('pending', 'rendering', 'ready', 'failed')"
    )
    op.execute(
        "CREATE TYPE proposal_status AS ENUM "
        "('rascunho', 'ready', 'aprovada', 'cancelada')"
    )
    op.execute(
        "CREATE TYPE parcela_payment_status AS ENUM "
        "('pending', 'paid', 'canceled')"
    )

    op.create_table(
        "proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id"), nullable=False),
        sa.Column("codigo", sa.Text, nullable=False),
        sa.Column("gerado_por", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("gerado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("validade_dias", sa.Integer,
                  server_default=sa.text("7"), nullable=False),
        sa.Column("snapshot_json", sa.JSON, nullable=False),
        sa.Column("pdf_key", sa.Text, nullable=True),
        sa.Column("carne_key", sa.Text, nullable=True),
        sa.Column("render_status",
                  sa.Enum("pending", "rendering", "ready", "failed",
                          name="proposal_render_status", create_type=False),
                  server_default=sa.text("'pending'"), nullable=False),
        sa.Column("render_error", sa.Text, nullable=True),
        sa.Column("status",
                  sa.Enum("rascunho", "ready", "aprovada", "cancelada",
                          name="proposal_status", create_type=False),
                  server_default=sa.text("'rascunho'"), nullable=False),
        sa.Column("aprovado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_proposals_tenant_codigo", "proposals", ["tenant_id", "codigo"]
    )
    op.create_unique_constraint(
        "uq_proposals_tenant_simulation", "proposals", ["tenant_id", "simulation_id"]
    )
    op.create_index("ix_proposals_tenant_gerado_em", "proposals",
                    ["tenant_id", "gerado_em"])

    op.create_table(
        "parcela_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parcela_num", sa.Integer, nullable=False),
        sa.Column("vencimento", sa.Date, nullable=False),
        sa.Column("valor_parcela", sa.Numeric(18, 2), nullable=False),
        sa.Column("status",
                  sa.Enum("pending", "paid", "canceled",
                          name="parcela_payment_status", create_type=False),
                  server_default=sa.text("'pending'"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pix_charge_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_parcela_payments_proposal_num", "parcela_payments",
                    ["proposal_id", "parcela_num"])


def downgrade() -> None:
    op.drop_table("parcela_payments")
    op.drop_table("proposals")
    op.execute("DROP TYPE IF EXISTS parcela_payment_status")
    op.execute("DROP TYPE IF EXISTS proposal_status")
    op.execute("DROP TYPE IF EXISTS proposal_render_status")
