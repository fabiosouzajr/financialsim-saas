"""add_carne_fields

Revision ID: a1b2c3d4e5f6
Revises: 45b4fea970eb
Create Date: 2026-05-27 00:00:00.000000

"""
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '45b4fea970eb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("proposals", sa.Column("carne_path", sa.String(), nullable=True))

    conn = op.get_bind()
    now = datetime.now(UTC).replace(tzinfo=None)
    loja_seeds = [
        ("nome_loja", '""', "Nome da loja"),
        ("cnpj_loja", '""', "CNPJ da loja"),
        ("endereco_loja", '""', "Endereço da loja"),
        ("telefone_loja", '""', "Telefone da loja"),
    ]
    for chave, valor_json, descricao in loja_seeds:
        existing = conn.execute(
            sa.text("SELECT id FROM business_rules WHERE chave = :chave"),
            {"chave": chave},
        ).first()
        if existing is None:
            conn.execute(
                sa.text(
                    "INSERT INTO business_rules (chave, valor_json, descricao, atualizado_em) "
                    "VALUES (:chave, :valor_json, :descricao, :atualizado_em)"
                ),
                {"chave": chave, "valor_json": valor_json,
                 "descricao": descricao, "atualizado_em": now},
            )


def downgrade() -> None:
    with op.batch_alter_table("proposals") as batch_op:
        batch_op.drop_column("carne_path")

    op.execute(
        "DELETE FROM business_rules WHERE chave IN "
        "('nome_loja','cnpj_loja','endereco_loja','telefone_loja')"
    )
