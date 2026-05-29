"""seed initial data

Revision ID: 85a5039acfca
Revises: f7c4f92f22d2
Create Date: 2026-05-24 09:16:20.239561

"""
from collections.abc import Sequence
from datetime import UTC

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '85a5039acfca'
down_revision: str | Sequence[str] | None = 'f7c4f92f22d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    import json
    from datetime import datetime

    import bcrypt

    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    conn = op.get_bind()

    # Admin user — PIN '123456' (must be changed on first login)
    pin_hash = bcrypt.hashpw(b"123456", bcrypt.gensalt()).decode()
    conn.execute(
        sa.text(
            "INSERT INTO users (nome, pin_hash, perfil, ativo, criado_em, atualizado_em) "
            "VALUES (:nome, :pin_hash, :perfil, :ativo, :criado_em, :atualizado_em)"
        ),
        {"nome": "Admin", "pin_hash": pin_hash, "perfil": "admin", "ativo": True,
         "criado_em": _utcnow(), "atualizado_em": _utcnow()},
    )

    defaults = [
        ("entrada_minima_pct", "0.10", "Entrada minima 10%"),
        ("prazo_minimo_meses", "12", "Prazo minimo"),
        ("prazo_maximo_meses", "72", "Prazo maximo"),
        ("taxa_minima_mes", "0.005", "0,5% a.m."),
        ("taxa_maxima_mes", "0.05", "5% a.m."),
        ("dias_max_carencia", "90", "Carencia maxima"),
        ("valor_minimo_financiado", "5000", "Valor minimo financiado"),
        ("incluir_iof_default", "true", "Default IOF ligado"),
        ("iof_fixo_pct", "0.0038", "IOF fixo 0,38%"),
        ("iof_diario_pct", "0.000082", "IOF diario 0,0082%/dia"),
        ("iof_diario_max_dias", "365", "Teto IOF diario por parcela"),
        ("taxa_por_prazo_curva", json.dumps([
            {"ate_meses": 24, "taxa_mensal": 0.0149},
            {"ate_meses": 36, "taxa_mensal": 0.0169},
            {"ate_meses": 48, "taxa_mensal": 0.0189},
            {"ate_meses": 60, "taxa_mensal": 0.0199},
            {"ate_meses": 72, "taxa_mensal": 0.0219},
        ]), "Curva de taxa por prazo"),
        ("extras_padrao", json.dumps([
            {"tipo": "protecao_veicular", "nome": "Plano de protecao veicular",
             "modalidade": "mensal_continuo", "valor_total_default": 0, "habilitado": True},
            {"tipo": "ipva", "nome": "IPVA anual (rateio)",
             "modalidade": "rateio_meses", "duracao_meses_default": 12,
             "valor_total_default": 0, "habilitado": True},
            {"tipo": "emplacamento", "nome": "Emplacamento + licenciamento (rateio)",
             "modalidade": "rateio_meses", "duracao_meses_default": 12,
             "valor_total_default": 0, "habilitado": True},
        ]), "Extras pre-cadastrados"),
        ("rateio_ipva_meses_default", "12", ""),
        ("rateio_emplacamento_meses_default", "12", ""),
        ("backup_diario_horario", '"23:00"', ""),
        ("backup_retencao_dias", "30", ""),
        ("update_indicadores_horario", '"09:00"', ""),
        ("fipe_cache_listas_ttl_dias", "30", ""),
        ("fipe_cache_preco_ttl_horas", "24", ""),
    ]
    for chave, valor_json, descricao in defaults:
        conn.execute(
            sa.text(
                "INSERT INTO business_rules (chave, valor_json, descricao, atualizado_em) "
                "VALUES (:chave, :valor_json, :descricao, :atualizado_em)"
            ),
            {"chave": chave, "valor_json": valor_json, "descricao": descricao,
             "atualizado_em": _utcnow()},
        )


def downgrade() -> None:
    op.execute("DELETE FROM business_rules")
    op.execute("DELETE FROM users WHERE nome = 'Admin'")
