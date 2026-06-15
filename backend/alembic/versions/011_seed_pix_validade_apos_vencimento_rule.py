"""seed pix_validade_apos_vencimento_dias business rule

Revision ID: 011
Revises: 010
Create Date: 2026-06-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_NEW_RULES = [
    ("pix_validade_apos_vencimento_dias", 60, "Dias de validade do Pix após o vencimento da parcela"),
]


def upgrade() -> None:
    for chave, valor, descricao in _NEW_RULES:
        op.execute(
            sa.text(
                """
                INSERT INTO business_rules (id, tenant_id, chave, valor_json, descricao, atualizado_em)
                SELECT gen_random_uuid(), t.id, :chave, cast(:valor as jsonb), :descricao, now()
                FROM tenants t
                ON CONFLICT (tenant_id, chave) DO NOTHING
                """
            ).bindparams(chave=chave, valor=str(valor), descricao=descricao)
        )


def downgrade() -> None:
    for chave, _, _ in _NEW_RULES:
        op.execute(
            sa.text("DELETE FROM business_rules WHERE chave = :chave").bindparams(chave=chave)
        )
