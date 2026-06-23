"""rename proposal_status 'ready' to 'pronta'

Revision ID: 013
Revises: 012
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE proposal_status RENAME VALUE 'ready' TO 'pronta'")


def downgrade() -> None:
    op.execute("ALTER TYPE proposal_status RENAME VALUE 'pronta' TO 'ready'")
