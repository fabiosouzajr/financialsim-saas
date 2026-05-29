"""add_vehicle_fields

Revision ID: 45b4fea970eb
Revises: 20d4cc8a430e
Create Date: 2026-05-26 14:09:09.432162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45b4fea970eb'
down_revision: Union[str, Sequence[str], None] = '20d4cc8a430e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column("vehicles", sa.Column("cor", sa.String(40), nullable=True))
    op.add_column("vehicles", sa.Column("placa", sa.String(10), nullable=True))
    op.add_column("vehicles", sa.Column("odometro_km", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("status", sa.String(20), nullable=True))
    op.add_column("vehicles", sa.Column("atualizado_em", sa.DateTime(), nullable=True))
    op.add_column("vehicles", sa.Column("criado_por", sa.Integer(), nullable=True))

    # Seed existing records
    # Business rule: all pre-existing manually-entered vehicles (fonte='manual') are
    # legacy simulation placeholders, not real inventory. Mark them as sold so they
    # don't appear in the active vehicle picker. New manual entries created after this
    # migration go through VehicleService and default to status='disponivel'.
    op.execute("""
        UPDATE vehicles
        SET status = 'vendido',
            atualizado_em = criado_em
        WHERE fonte = 'manual'
    """)
    op.execute("""
        UPDATE vehicles
        SET status = 'disponivel',
            atualizado_em = criado_em
        WHERE fonte != 'manual' AND status IS NULL
    """)

    # Make status non-nullable after seeding (SQLite requires batch mode)
    with op.batch_alter_table("vehicles") as batch_op:
        batch_op.alter_column("status", nullable=False)

    # Partial unique index: placa unique only among active vehicles
    op.execute("""
        CREATE UNIQUE INDEX uq_vehicles_placa_ativa
        ON vehicles (placa)
        WHERE status != 'vendido' AND placa IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_vehicles_placa_ativa")
    op.drop_column("vehicles", "criado_por")
    op.drop_column("vehicles", "atualizado_em")
    op.drop_column("vehicles", "status")
    op.drop_column("vehicles", "odometro_km")
    op.drop_column("vehicles", "placa")
    op.drop_column("vehicles", "cor")
