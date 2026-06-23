"""add company profile columns to tenants

Revision ID: 014
Revises: 013
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("cnpj", sa.String(18), nullable=True))
    op.add_column("tenants", sa.Column("telefone", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("endereco", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("logo_key", sa.Text(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column(
            "proposta_validade_dias",
            sa.Integer(),
            nullable=False,
            server_default="15",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "proposta_validade_dias")
    op.drop_column("tenants", "logo_key")
    op.drop_column("tenants", "endereco")
    op.drop_column("tenants", "telefone")
    op.drop_column("tenants", "cnpj")
