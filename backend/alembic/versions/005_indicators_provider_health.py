"""indicators_history and provider_health tables

Revision ID: 005
Revises: 004
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "indicators_history",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(10, 6), nullable=False),
        sa.Column("unidade", sa.Text(), nullable=False),
        sa.Column("fonte", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "coletado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "codigo", "data_referencia", name="uq_indicators_history_codigo_date"
        ),
    )
    op.create_table(
        "provider_health",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("provider_name", sa.Text(), nullable=False),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_health_name_checked", "provider_health",
        ["provider_name", "checked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_health_name_checked", table_name="provider_health")
    op.drop_table("provider_health")
    op.drop_table("indicators_history")
