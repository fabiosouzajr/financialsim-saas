"""auth tables — users, password_reset_tokens, refresh_tokens, audit_log, notifications_outbox

Revision ID: 002
Revises: 001
Create Date: 2026-05-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute(
        "CREATE TYPE userrole AS ENUM ('admin', 'manager', 'user', 'customer')"
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", CITEXT, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Enum(name="userrole", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("tokens_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_users_email_staff ON users (email) WHERE role != 'customer'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_users_tenant_email_customer"
        " ON users (tenant_id, email) WHERE role = 'customer'"
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("usuario_id", UUID(as_uuid=True), nullable=True),
        sa.Column("acao", sa.Text, nullable=False),
        sa.Column("entidade", sa.Text, nullable=True),
        sa.Column("entidade_id", UUID(as_uuid=True), nullable=True),
        sa.Column("diff_json", sa.JSON, nullable=True),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("hostname", sa.Text, nullable=True),
    )
    op.create_index("ix_audit_log_tenant_timestamp", "audit_log", ["tenant_id", "timestamp"])
    op.create_index(
        "ix_audit_log_tenant_entidade", "audit_log",
        ["tenant_id", "entidade", "entidade_id"],
    )

    op.create_table(
        "notifications_outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("recipient", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("notifications_outbox")
    op.drop_table("audit_log")
    op.drop_table("refresh_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("users")
    op.execute("DROP TYPE userrole")
