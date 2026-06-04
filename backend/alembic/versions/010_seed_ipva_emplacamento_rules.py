"""seed IPVA and emplacamento business rules for all tenants

Revision ID: 010
Revises: 009
Create Date: 2026-06-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009_system_settings"
branch_labels = None
depends_on = None

_NEW_RULES = [
    ("ipva_pct_carro",           "0.035",  "IPVA — alíquota carro (% a.a.)"),
    ("ipva_pct_moto",            "0.030",  "IPVA — alíquota moto (% a.a.)"),
    ("ipva_pct_caminhao",        "0.010",  "IPVA — alíquota caminhão (% a.a.)"),
    ("emplacamento_valor_carro",   "220.46", "Emplacamento — carro (R$)"),
    ("emplacamento_valor_moto",    "188.96", "Emplacamento — moto (R$)"),
    ("emplacamento_valor_caminhao","220.46", "Emplacamento — caminhão (R$)"),
]


def upgrade() -> None:
    for chave, valor, descricao in _NEW_RULES:
        op.execute(
            sa.text(
                """
                INSERT INTO business_rules
                    (id, tenant_id, chave, valor_json, descricao, atualizado_em)
                SELECT gen_random_uuid(), t.id, :chave, cast(:valor as jsonb), :descricao, now()
                FROM tenants t
                ON CONFLICT (tenant_id, chave) DO NOTHING
                """
            ).bindparams(chave=chave, valor=f'"{valor}"', descricao=descricao)
        )


def downgrade() -> None:
    for chave, _, _ in _NEW_RULES:
        op.execute(
            sa.text("DELETE FROM business_rules WHERE chave = :chave").bindparams(chave=chave)
        )
