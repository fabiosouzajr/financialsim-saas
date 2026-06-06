# Phase 6A — Data Layer + Pix Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add migration 007 (schema changes), update models, add PIX settings, and create the `pix/` module with protocol, fake provider, stub, and deps.

**Architecture:** Migration alters the `parcela_payment_status` enum, renames a column, adds new tables (`pix_charges`, `pix_webhook_events`). Model changes mirror migration. Pix module mirrors the `storage/` pattern: a Protocol, two providers (fake + stub), and a deps factory.

**Tech Stack:** PostgreSQL (Alembic), SQLAlchemy 2.x mapped_column, `qrcode` library for PNG generation, Python 3.12.

**Predecessor plans in this series:**
- 6B: `2026-06-02-saas-phase-6b-services.md`
- 6C: `2026-06-02-saas-phase-6c-api.md`
- 6D: `2026-06-02-saas-phase-6d-frontend.md`
- 6E: `2026-06-02-saas-phase-6e-tests.md`

---

### Task 1: Add `qrcode` dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add qrcode to dependencies**

In `backend/pyproject.toml`, add `"qrcode>=7.4.2"` to the `dependencies` list (after `jinja2`):

```toml
    "jinja2>=3.1.0",
    "qrcode>=7.4.2",
```

- [ ] **Step 2: Sync dependencies**

```bash
cd /home/fabio/git/financialsim-saas && uv sync --extra dev
```
Expected: resolves without error, `qrcode` appears in lock.

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml uv.lock
git commit -m "chore: add qrcode dependency for Pix QR PNG generation"
```

---

### Task 2: Migration 007

**Files:**
- Create: `backend/alembic/versions/007_phase6_pix.py`

- [ ] **Step 1: Create migration file**

```python
"""phase6 — pix_charges, pix_webhook_events, parcela_payments updates

Revision ID: 007
Revises: 006
Create Date: 2026-06-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename parcela_payment_status 'pending' → 'open'
    op.execute(
        "ALTER TYPE parcela_payment_status RENAME VALUE 'pending' TO 'open'"
    )
    # 2. Add 'overdue' to parcela_payment_status
    op.execute(
        "ALTER TYPE parcela_payment_status ADD VALUE IF NOT EXISTS 'overdue'"
    )
    # 3. Rename column pix_charge_id → last_pix_charge_id on parcela_payments
    op.alter_column(
        "parcela_payments", "pix_charge_id",
        new_column_name="last_pix_charge_id",
    )
    # 4. Add paid_amount nullable column to parcela_payments
    op.add_column(
        "parcela_payments",
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=True),
    )

    # 5. Create pix_charge_status enum
    op.execute(
        "CREATE TYPE pix_charge_status AS ENUM "
        "('pending', 'paid', 'expired', 'canceled')"
    )

    # 6. Create pix_charges table
    op.create_table(
        "pix_charges",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "parcela_payment_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("parcela_payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("txid", sa.Text, nullable=False),
        sa.Column("brcode", sa.Text, nullable=False),
        sa.Column("qrcode_png_key", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "paid", "expired", "canceled",
                name="pix_charge_status", create_type=False,
            ),
            nullable=False, server_default=sa.text("'pending'"),
        ),
        sa.Column("provider_payload_json", sa.JSON, nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "atualizado_em", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_unique_constraint("uq_pix_charges_txid", "pix_charges", ["txid"])
    op.create_index("ix_pix_charges_parcela", "pix_charges", ["parcela_payment_id"])
    op.create_index("ix_pix_charges_tenant_status", "pix_charges", ["tenant_id", "status"])

    # 7. Create pix_webhook_events table
    op.create_table(
        "pix_webhook_events",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "received_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("signature_valid", sa.Boolean, nullable=False),
        sa.Column("headers_json", sa.JSON, nullable=False),
        sa.Column("body_json", sa.JSON, nullable=False),
        sa.Column(
            "processed", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_pix_webhook_events_received", "pix_webhook_events", ["received_at"]
    )


def downgrade() -> None:
    op.drop_table("pix_webhook_events")
    op.drop_table("pix_charges")
    op.execute("DROP TYPE IF EXISTS pix_charge_status")
    op.drop_column("parcela_payments", "paid_amount")
    op.alter_column(
        "parcela_payments", "last_pix_charge_id",
        new_column_name="pix_charge_id",
    )
    op.execute(
        "ALTER TYPE parcela_payment_status RENAME VALUE 'open' TO 'pending'"
    )
    # Note: cannot remove 'overdue' from enum in Postgres without recreating it.
    # For dev, drop and recreate; for prod, this is irreversible without data migration.
```

- [ ] **Step 2: Verify migration runs**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend alembic -c backend/alembic.ini upgrade head
```
Expected: migration applies without error.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/007_phase6_pix.py
git commit -m "feat(phase6): migration 007 — pix tables, parcela_payment_status overdue"
```

---

### Task 3: Update models.py

**Files:**
- Modify: `backend/finacialsim_saas/data/models.py`

- [ ] **Step 1: Update ParcelaPaymentStatus enum**

Replace the current `ParcelaPaymentStatus` class:

```python
class ParcelaPaymentStatus(enum.Enum):
    pending = "pending"
    paid = "paid"
    canceled = "canceled"
```

With:

```python
class ParcelaPaymentStatus(enum.Enum):
    open = "open"
    paid = "paid"
    canceled = "canceled"
    overdue = "overdue"
```

- [ ] **Step 2: Add PixChargeStatus enum** (add after `ParcelaPaymentStatus`)

```python
class PixChargeStatus(enum.Enum):
    pending = "pending"
    paid = "paid"
    expired = "expired"
    canceled = "canceled"
```

- [ ] **Step 3: Update ParcelaPayment model**

Replace:
```python
    status: Mapped[ParcelaPaymentStatus] = mapped_column(
        sa.Enum(ParcelaPaymentStatus, name="parcela_payment_status", native_enum=True),
        nullable=False, server_default=sa.text("'pending'"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    pix_charge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

With:
```python
    status: Mapped[ParcelaPaymentStatus] = mapped_column(
        sa.Enum(ParcelaPaymentStatus, name="parcela_payment_status", native_enum=True),
        nullable=False, server_default=sa.text("'open'"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    last_pix_charge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

- [ ] **Step 4: Add PixCharge model** (add after `ParcelaPayment` class)

```python
class PixCharge(Base):
    __tablename__ = "pix_charges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parcela_payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("parcela_payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    txid: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    brcode: Mapped[str] = mapped_column(sa.Text, nullable=False)
    qrcode_png_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    status: Mapped[PixChargeStatus] = mapped_column(
        sa.Enum(PixChargeStatus, name="pix_charge_status", native_enum=True),
        nullable=False, server_default=sa.text("'pending'"),
    )
    provider_payload_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.Index("ix_pix_charges_parcela", "parcela_payment_id"),
        sa.Index("ix_pix_charges_tenant_status", "tenant_id", "status"),
    )


class PixWebhookEvent(Base):
    __tablename__ = "pix_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    signature_valid: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    headers_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    body_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
```

- [ ] **Step 5: Run models import test**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.data.models import PixCharge, PixWebhookEvent, ParcelaPaymentStatus, PixChargeStatus; print('OK', ParcelaPaymentStatus.open, PixChargeStatus.pending)"
```
Expected: `OK ParcelaPaymentStatus.open PixChargeStatus.pending`

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/data/models.py
git commit -m "feat(phase6): add PixCharge, PixWebhookEvent models; update ParcelaPaymentStatus"
```

---

### Task 4: Update Settings

**Files:**
- Modify: `backend/finacialsim_saas/settings.py`

- [ ] **Step 1: Add Pix settings**

Add after `storage_base_url`:

```python
    pix_provider: str = "fake"
    pix_webhook_secret: str = ""
```

- [ ] **Step 2: Verify settings load**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.settings import get_settings; s = get_settings(); print(s.pix_provider, repr(s.pix_webhook_secret))"
```
Expected: `fake ''`

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/settings.py
git commit -m "feat(phase6): add PIX_PROVIDER and PIX_WEBHOOK_SECRET settings"
```

---

### Task 5: Create pix/protocol.py

**Files:**
- Create: `backend/finacialsim_saas/pix/__init__.py`
- Create: `backend/finacialsim_saas/pix/protocol.py`

- [ ] **Step 1: Create pix/__init__.py**

```python
from finacialsim_saas.pix.protocol import PixChargeData, PixProvider, WebhookEvent

__all__ = ["PixProvider", "PixChargeData", "WebhookEvent"]
```

- [ ] **Step 2: Create pix/protocol.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass
class PixChargeData:
    """Value object returned by PixProvider.create_charge."""
    txid: str
    brcode: str
    qr_png_bytes: bytes
    amount: Decimal
    expires_at: datetime
    provider_payload: dict = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """Parsed result of PixProvider.verify_webhook."""
    txid: str
    status: str  # "paid" | "expired" | "canceled"
    paid_amount: Decimal | None = None
    provider_payload: dict = field(default_factory=dict)


@runtime_checkable
class PixProvider(Protocol):
    name: str

    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: str,
    ) -> PixChargeData: ...

    async def cancel_charge(self, txid: str) -> None: ...

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent: ...
```

- [ ] **Step 3: Verify import**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "from finacialsim_saas.pix import PixProvider, PixChargeData, WebhookEvent; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/pix/
git commit -m "feat(phase6): add pix/ module with PixProvider protocol"
```

---

### Task 6: Create pix/fake.py

**Files:**
- Create: `backend/finacialsim_saas/pix/fake.py`

- [ ] **Step 1: Create fake.py**

```python
from __future__ import annotations

import hashlib
import hmac
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import qrcode
from qrcode.image.pure import PyPNGImage

from finacialsim_saas.pix.protocol import PixChargeData, WebhookEvent

UTC = timezone.utc


class InMemoryFakePixProvider:
    name = "fake"

    def __init__(self, secret: str = "") -> None:
        self._secret = secret

    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: str,
    ) -> PixChargeData:
        brcode = (
            f"00020126330014BR.GOV.BCB.PIX0114{txid[:14]}"
            f"5204000053039865802BR5913{description[:13]}"
            f"6009SAOPAULO62070503***63040000"
        )
        buf = io.BytesIO()
        img = qrcode.make(brcode, image_factory=PyPNGImage)
        img.save(buf)
        qr_png = buf.getvalue()

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return PixChargeData(
            txid=txid,
            brcode=brcode,
            qr_png_bytes=qr_png,
            amount=amount,
            expires_at=expires_at,
        )

    async def cancel_charge(self, txid: str) -> None:
        pass  # no-op for fake

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent:
        if self._secret:
            sig_header = headers.get("X-Pix-Signature", "")
            if not sig_header.startswith("sha256="):
                raise ValueError("Missing or invalid X-Pix-Signature header")
            expected = "sha256=" + hmac.new(
                self._secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                raise ValueError("Invalid HMAC-SHA256 signature")

        payload = json.loads(body)
        pix_entries = payload.get("pix", [])
        if not pix_entries:
            raise ValueError("No pix entries in webhook payload")
        entry = pix_entries[0]
        paid_amount = Decimal(str(entry["valor"])) if "valor" in entry else None
        return WebhookEvent(
            txid=entry["txid"],
            status=entry["status"],
            paid_amount=paid_amount,
            provider_payload=entry,
        )
```

- [ ] **Step 2: Smoke test fake provider**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "
import asyncio
from decimal import Decimal
from finacialsim_saas.pix.fake import InMemoryFakePixProvider

async def test():
    p = InMemoryFakePixProvider()
    charge = await p.create_charge(txid='test123', amount=Decimal('500.00'), expires_in=1800, description='Parcela 1', payer='')
    print('brcode:', charge.brcode[:40])
    print('qr_png bytes:', len(charge.qr_png_bytes))
    assert len(charge.qr_png_bytes) > 0
    print('OK')

asyncio.run(test())
"
```
Expected: prints brcode, qr_png bytes count, OK.

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/pix/fake.py
git commit -m "feat(phase6): add InMemoryFakePixProvider with real QR PNG generation"
```

---

### Task 7: Create pix/stub.py and pix/deps.py

**Files:**
- Create: `backend/finacialsim_saas/pix/stub.py`
- Create: `backend/finacialsim_saas/pix/deps.py`

- [ ] **Step 1: Create stub.py**

```python
from __future__ import annotations

from decimal import Decimal

from finacialsim_saas.pix.protocol import PixChargeData, WebhookEvent


class StubExternalPixProvider:
    name = "external"

    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: str,
    ) -> PixChargeData:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")

    async def cancel_charge(self, txid: str) -> None:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent:
        raise NotImplementedError("External Pix provider not wired — set PIX_PROVIDER=fake")
```

- [ ] **Step 2: Create deps.py**

```python
from __future__ import annotations

from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.pix.stub import StubExternalPixProvider
from finacialsim_saas.settings import Settings


def get_pix_provider(settings: Settings) -> PixProvider:
    if settings.pix_provider == "fake":
        return InMemoryFakePixProvider(secret=settings.pix_webhook_secret)
    if settings.pix_provider == "external":
        return StubExternalPixProvider()
    raise ValueError(f"Unknown PIX_PROVIDER: {settings.pix_provider!r}")
```

- [ ] **Step 3: Verify deps**

```bash
cd /home/fabio/git/financialsim-saas && uv run --directory backend python -c "
from finacialsim_saas.settings import get_settings
from finacialsim_saas.pix.deps import get_pix_provider
p = get_pix_provider(get_settings())
print('provider:', p.name)
"
```
Expected: `provider: fake`

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/pix/stub.py backend/finacialsim_saas/pix/deps.py
git commit -m "feat(phase6): add StubExternalPixProvider and get_pix_provider deps"
```

---

### Task 8: Update proposal_service.py pending→open references

**Files:**
- Modify: `backend/finacialsim_saas/services/proposal_service.py`

The enum rename from `pending` → `open` breaks `approve()` which creates `ParcelaPayment(status=ParcelaPaymentStatus.pending)`.

- [ ] **Step 1: Update status in approve()**

Replace in `approve()`:
```python
                    status=ParcelaPaymentStatus.pending,
```
With:
```python
                    status=ParcelaPaymentStatus.open,
```

- [ ] **Step 2: Run existing proposal tests to confirm no regressions**

```bash
cd /home/fabio/git/financialsim-saas/backend && uv run pytest tests/test_proposal_service.py tests/test_proposal_endpoints.py -x -q
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/services/proposal_service.py
git commit -m "fix(phase6): update ParcelaPaymentStatus.pending → open after enum rename"
```
