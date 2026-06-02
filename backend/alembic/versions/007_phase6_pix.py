"""phase6 — pix_charges, pix_webhook_events, parcela_payments updates

Revision ID: 007
Revises: 006
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename parcela_payment_status 'pending' → 'open'
    op.execute(
        "ALTER TYPE parcela_payment_status RENAME VALUE 'pending' TO 'open'"
    )
    # 2. Add 'overdue' to parcela_payment_status
    op.execute(
        "ALTER TYPE parcela_payment_status ADD VALUE IF NOT EXISTS 'overdue'"
    )
    # 3. Rename column pix_charge_id → last_pix_charge_id on parcela_payments
    op.alter_column(
        "parcela_payments", "pix_charge_id",
        new_column_name="last_pix_charge_id",
    )
    # 4. Add paid_amount nullable column to parcela_payments
    op.add_column(
        "parcela_payments",
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=True),
    )

    # 5. Create pix_charge_status enum
    op.execute(
        "CREATE TYPE pix_charge_status AS ENUM "
        "('pending', 'paid', 'expired', 'canceled')"
    )

    # 6. Create pix_charges table
    op.create_table(
        "pix_charges",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "parcela_payment_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("parcela_payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("txid", sa.Text, nullable=False),
        sa.Column("brcode", sa.Text, nullable=False),
        sa.Column("qrcode_png_key", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="pix_charge_status", create_type=False),
            nullable=False, server_default=sa.text("'pending'"),
        ),
        sa.Column("provider_payload_json", sa.JSON, nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "atualizado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_unique_constraint("uq_pix_charges_txid", "pix_charges", ["txid"])
    op.create_index("ix_pix_charges_parcela", "pix_charges", ["parcela_payment_id"])
    op.create_index("ix_pix_charges_tenant_status", "pix_charges", ["tenant_id", "status"])

    # 7. Create pix_webhook_events table
    op.create_table(
        "pix_webhook_events",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "received_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("signature_valid", sa.Boolean, nullable=False),
        sa.Column("headers_json", sa.JSON, nullable=False),
        sa.Column("body_json", sa.JSON, nullable=False),
        sa.Column(
            "processed", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_pix_webhook_events_received", "pix_webhook_events", ["received_at"]
    )


def downgrade() -> None:
    op.drop_table("pix_webhook_events")
    op.drop_table("pix_charges")
    op.execute("DROP TYPE IF EXISTS pix_charge_status")
    op.drop_column("parcela_payments", "paid_amount")
    op.alter_column(
        "parcela_payments", "last_pix_charge_id",
        new_column_name="pix_charge_id",
    )
    op.execute(
        "ALTER TYPE parcela_payment_status RENAME VALUE 'open' TO 'pending'"
    )
    # Note: cannot remove 'overdue' from enum in Postgres without recreating it.
