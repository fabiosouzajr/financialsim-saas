"""phase7 — finalize notifications_outbox schema; add email_log stub

Revision ID: 008
Revises: 007
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop placeholder outbox (dev env only — no prod data to preserve)
    op.drop_table("notifications_outbox")

    # Recreate with finalized schema
    op.create_table(
        "notifications_outbox",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text, nullable=False, server_default="email"),
        sa.Column("template_key", sa.Text, nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=False),
        sa.Column("target_email", sa.Text, nullable=True),
        sa.Column("target_phone", sa.Text, nullable=True),
        sa.Column(
            "scheduled_for", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_notifications_outbox_status_scheduled",
        "notifications_outbox", ["status", "scheduled_for"],
    )
    op.create_index("ix_notifications_outbox_tenant", "notifications_outbox", ["tenant_id"])
    op.create_unique_constraint(
        "uq_notifications_outbox_idempotency_key",
        "notifications_outbox", ["idempotency_key"],
    )

    # email_log — stub table for future delivery-callback writes
    op.create_table(
        "email_log",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "outbox_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications_outbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_message_id", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=True),
        sa.Column("provider_payload_json", sa.JSON, nullable=True),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index("ix_email_log_outbox_id", "email_log", ["outbox_id"])
    op.create_index("ix_email_log_tenant", "email_log", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("email_log")
    op.drop_table("notifications_outbox")
    # Note: original notifications_outbox schema from migration 002 is not restored.
