"""seed inadimplencia business rules for all tenants

Revision ID: 012
Revises: 011
Create Date: 2026-06-15
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

_NEW_RULES = [
    ("inadimplencia_multa_pct",          "0.00", "Multa por inadimplência (%, máx 2%)"),
    ("inadimplencia_juros_diario_pct",   "0.00", "Juros moratórios diários (%, máx 0.1%)"),
    ("inadimplencia_carencia_dias",      0,      "Carência antes dos encargos (dias, máx 30)"),
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
            ).bindparams(chave=chave, valor=json.dumps(valor), descricao=descricao)
        )


def downgrade() -> None:
    for chave, _, _ in _NEW_RULES:
        op.execute(
            sa.text("DELETE FROM business_rules WHERE chave = :chave").bindparams(chave=chave)
        )
