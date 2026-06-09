# Fase 3 — Inadimplência Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable multa + juros moratórios to overdue Pix CobV charges, with per-tenant grace period (carência), daily charge regeneration for accurate interest accrual, and portal-side real-time encargos estimate.

**Architecture:** Three business rules drive everything (`inadimplencia_multa_pct`, `inadimplencia_juros_diario_pct`, `inadimplencia_carencia_dias`). The `_ensure_charge` method extracted from `PixService.create_charge_for_parcela` reads these rules, enforces the grace period gate, and regenerates stale overdue charges daily so the brcode always reflects current interest. `_calculate_overdue_amount` is a pure function in `parcela_service.py` that computes the portal estimate without touching the DB. Phase 1 (EfiPixProvider real implementation) is a separate concern — this plan adds the penalty params to the Protocol and lets them flow through; the fake provider accepts and ignores them.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, pytest-asyncio, testcontainers-postgres

---

## Prerequisite

The fake provider (`InMemoryFakePixProvider`) is used throughout. When Phase 1 (EfiPixProvider) is implemented later, it will use the penalty params to build the CobV body with `modalidade: 2` for both multa and juros.

---

## File Map

| Action   | File                                                                    | What changes                                         |
|----------|-------------------------------------------------------------------------|------------------------------------------------------|
| Modify   | `backend/finacialsim_saas/services/rules_service.py`                   | Add 3 defaults, 3 validators, validation logic       |
| Create   | `backend/alembic/versions/011_seed_inadimplencia_rules.py`             | Seed migration for all existing tenants              |
| Modify   | `backend/finacialsim_saas/schemas/business_rules.py`                   | 3 new fields on `BusinessRulesOut`                   |
| Modify   | `backend/finacialsim_saas/api/business_rules.py`                       | 3 new kwargs in `get_business_rules`                 |
| Modify   | `backend/finacialsim_saas/pix/protocol.py`                             | 3 new keyword params on `PixProvider.create_charge`  |
| Modify   | `backend/finacialsim_saas/pix/fake.py`                                 | Accept + ignore 3 new params                         |
| Modify   | `backend/finacialsim_saas/pix/service.py`                              | Extract `_ensure_charge`, add penalty + regeneration |
| Modify   | `backend/finacialsim_saas/services/parcela_service.py`                 | Add `_calculate_overdue_amount`, enrich `get_schedule`|
| Modify   | `backend/finacialsim_saas/api/portal.py`                               | Enrich `get_parcela` with effective status + encargos|
| Create   | `backend/tests/test_inadimplencia_rules.py`                            | Tests for validation guards + schema endpoint        |
| Create   | `backend/tests/test_pix_service_inadimplencia.py`                      | Integration tests for `_ensure_charge` regeneration  |
| Create   | `backend/tests/test_inadimplencia_overdue_amount.py`                   | Unit tests for `_calculate_overdue_amount`           |

---

## Task 1: Business Rule Defaults + Seed Migration

**Files:**
- Modify: `backend/finacialsim_saas/services/rules_service.py:14-42` (add to `_RULE_DEFAULTS`)
- Create: `backend/alembic/versions/011_seed_inadimplencia_rules.py`

- [ ] **Step 1: Add three entries to `_RULE_DEFAULTS`**

In `rules_service.py`, append three entries to `_RULE_DEFAULTS` (inside the dict literal, after the existing entries):

```python
    "inadimplencia_multa_pct":          ("0.00",  "Multa por inadimplência (%, máx 2%)"),
    "inadimplencia_juros_diario_pct":   ("0.00",  "Juros moratórios diários (%, máx 0.1%)"),
    "inadimplencia_carencia_dias":      (0,       "Carência antes dos encargos (dias, máx 30)"),
```

- [ ] **Step 2: Create seed migration**

Create `backend/alembic/versions/011_seed_inadimplencia_rules.py` with this content:

```python
"""seed inadimplencia business rules for all tenants

Revision ID: 011
Revises: 010
Create Date: 2026-06-09
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
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
```

Note: `json.dumps("0.00")` → `'"0.00"'` (JSON string), `json.dumps(0)` → `'0'` (JSON number). This ensures correct jsonb types for each field.

- [ ] **Step 3: Verify rules are readable with defaults**

Run:
```bash
cd backend && python -c "
from finacialsim_saas.services.rules_service import _RULE_DEFAULTS
assert 'inadimplencia_multa_pct' in _RULE_DEFAULTS
assert 'inadimplencia_juros_diario_pct' in _RULE_DEFAULTS
assert 'inadimplencia_carencia_dias' in _RULE_DEFAULTS
print('OK:', _RULE_DEFAULTS['inadimplencia_multa_pct'], _RULE_DEFAULTS['inadimplencia_carencia_dias'])
"
```
Expected: `OK: ('0.00', ...) (0, ...)`

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/services/rules_service.py \
        backend/alembic/versions/011_seed_inadimplencia_rules.py
git commit -m "feat(inadimplencia): add 3 business rule defaults + seed migration 011"
```

---

## Task 2: Validation Guards in RulesService.update()

**Files:**
- Modify: `backend/finacialsim_saas/services/rules_service.py` (add `_RULE_VALIDATORS` + check in `update`)
- Create: `backend/tests/test_inadimplencia_rules.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_inadimplencia_rules.py`:

```python
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings


async def _seed_tenant(engine: AsyncEngine) -> tuple[uuid.UUID, str]:
    from finacialsim_saas.cli.main import _seed_business_rules

    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"InadTest-{uuid.uuid4().hex[:6]}", slug=f"inad-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        await _seed_business_rules(session, t.id)
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id, email=f"u-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Admin", role=Role.admin,
        )
        await session.flush()
        token, _ = await svc.issue_tokens(user)
        await session.commit()
        return t.id, token


@pytest.mark.asyncio
async def test_multa_pct_above_ceiling_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_multa_pct",
        json={"valor": "2.01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_juros_pct_above_ceiling_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_juros_diario_pct",
        json={"valor": "0.11"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_carencia_dias_above_ceiling_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_carencia_dias",
        json={"valor": 31},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_valid_multa_pct_accepted(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_multa_pct",
        json={"valor": "2.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_negative_multa_rejected(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_tenant(engine)
    resp = await client.put(
        "/api/v1/business-rules/inadimplencia_multa_pct",
        json={"valor": "-0.01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_inadimplencia_rules.py -v
```
Expected: all 5 tests fail (validation not implemented yet).

- [ ] **Step 3: Add `_RULE_VALIDATORS` and validation in `rules_service.py`**

After `_REQUIRED_RULES = frozenset(_RULE_DEFAULTS.keys())`, add:

```python
_RULE_VALIDATORS: dict[str, tuple[float, float]] = {
    "inadimplencia_multa_pct":          (0.0, 2.0),
    "inadimplencia_juros_diario_pct":   (0.0, 0.1),
    "inadimplencia_carencia_dias":      (0.0, 30.0),
}
```

In `RulesService.update()`, add a range check before the DB operations. Insert after the `if chave not in _RULE_DEFAULTS` block and before any DB write. The full `update` method body should begin:

```python
    async def update(
        self,
        chave: str,
        valor: Any,
        ctx: RequestContext,
        motivo: str | None = None,
        redis: Any | None = None,
    ) -> None:
        if chave not in _RULE_DEFAULTS:
            from finacialsim_saas.errors import AppError
            raise AppError(f"business rule not found: {chave}")

        if chave in _RULE_VALIDATORS:
            lo, hi = _RULE_VALIDATORS[chave]
            try:
                num = float(valor)
            except (TypeError, ValueError):
                from finacialsim_saas.errors import ValidationError
                raise ValidationError(f"{chave} must be a number between {lo} and {hi}")
            if not (lo <= num <= hi):
                from finacialsim_saas.errors import ValidationError
                raise ValidationError(f"{chave} must be between {lo} and {hi}")

        result = await self._s.execute(
            select(BusinessRule).where(
                BusinessRule.tenant_id == ctx.tenant_id,
                BusinessRule.chave == chave,
            )
        )
        # ... rest unchanged
```

Note: The existing `update()` has an `AppError` raise for unknown keys inside the `if rule is None` branch. Move that check to the top of the method (before the DB query) as shown above — this is cleaner and avoids a DB round-trip for unknown keys.

The existing `if rule is None` block currently does:
```python
if rule is None:
    if chave not in _RULE_DEFAULTS:
        raise AppError(...)
    _, descricao = _RULE_DEFAULTS[chave]
    ...
```
After the refactor, the `if chave not in _RULE_DEFAULTS` check moves to the top, and `if rule is None` becomes:
```python
if rule is None:
    _, descricao = _RULE_DEFAULTS[chave]
    rule = BusinessRule(...)
    self._s.add(rule)
    await audit.log(...)
else:
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_inadimplencia_rules.py -v
```
Expected: all 5 tests pass.

- [ ] **Step 5: Run existing rules tests to check no regression**

```bash
cd backend && python -m pytest tests/test_business_rules_update.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/rules_service.py \
        backend/tests/test_inadimplencia_rules.py
git commit -m "feat(inadimplencia): add range validation guards for 3 penalty rules"
```

---

## Task 3: Schema + API Endpoint Additions

**Files:**
- Modify: `backend/finacialsim_saas/schemas/business_rules.py`
- Modify: `backend/finacialsim_saas/api/business_rules.py`

- [ ] **Step 1: Write a failing test for the new fields**

Append to `backend/tests/test_inadimplencia_rules.py`:

```python
@pytest.mark.asyncio
async def test_business_rules_get_includes_inadimplencia_defaults(
    client: AsyncClient, engine: AsyncEngine
):
    _, token = await _seed_tenant(engine)
    resp = await client.get(
        "/api/v1/business-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inadimplencia_multa_pct"] == "0.00"
    assert data["inadimplencia_juros_diario_pct"] == "0.00"
    assert data["inadimplencia_carencia_dias"] == 0
```

Run it:
```bash
cd backend && python -m pytest tests/test_inadimplencia_rules.py::test_business_rules_get_includes_inadimplencia_defaults -v
```
Expected: FAIL (fields not in schema yet).

- [ ] **Step 2: Add 3 fields to `BusinessRulesOut`**

In `backend/finacialsim_saas/schemas/business_rules.py`, append to `BusinessRulesOut` after `emplacamento_valor_caminhao`:

```python
    inadimplencia_multa_pct: DecimalStr
    inadimplencia_juros_diario_pct: DecimalStr
    inadimplencia_carencia_dias: int
```

- [ ] **Step 3: Add 3 kwargs to `get_business_rules`**

In `backend/finacialsim_saas/api/business_rules.py`, add to the `BusinessRulesOut(...)` constructor call, after `emplacamento_valor_caminhao=rules["emplacamento_valor_caminhao"]`:

```python
        inadimplencia_multa_pct=rules["inadimplencia_multa_pct"],
        inadimplencia_juros_diario_pct=rules["inadimplencia_juros_diario_pct"],
        inadimplencia_carencia_dias=int(rules["inadimplencia_carencia_dias"]),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_inadimplencia_rules.py -v
```
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/schemas/business_rules.py \
        backend/finacialsim_saas/api/business_rules.py \
        backend/tests/test_inadimplencia_rules.py
git commit -m "feat(inadimplencia): expose 3 penalty rule fields in BusinessRulesOut"
```

---

## Task 4: Protocol + Fake Provider

**Files:**
- Modify: `backend/finacialsim_saas/pix/protocol.py`
- Modify: `backend/finacialsim_saas/pix/fake.py`

- [ ] **Step 1: Add 3 penalty params to `PixProvider.create_charge`**

Replace the `create_charge` signature in `protocol.py`:

```python
    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: str,
        multa_pct: Decimal,
        juros_diario_pct: Decimal,
        carencia_dias: int,
    ) -> PixChargeData: ...
```

- [ ] **Step 2: Update `InMemoryFakePixProvider.create_charge`**

Replace the `create_charge` signature in `fake.py` to match, adding the 3 new params at the end (they are ignored by the fake):

```python
    async def create_charge(
        self,
        *,
        txid: str,
        amount: Decimal,
        expires_in: int,
        description: str,
        payer: str,
        multa_pct: Decimal,
        juros_diario_pct: Decimal,
        carencia_dias: int,
    ) -> PixChargeData:
        brcode = (
            f"00020126330014BR.GOV.BCB.PIX0114{txid[:14]}"
            f"5204000053039865802BR5913{description[:13]}"
            f"6009SAOPAULO62070503***63040000"
        )
        buf = io.BytesIO()
        img = qrcode.make(brcode, image_factory=PilImage)
        img.save(buf, format="PNG")
        qr_png = buf.getvalue()

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return PixChargeData(
            txid=txid,
            brcode=brcode,
            qr_png_bytes=qr_png,
            amount=amount,
            expires_at=expires_at,
        )
```

- [ ] **Step 3: Type-check pix package**

```bash
cd backend && python -m mypy finacialsim_saas/pix/ --ignore-missing-imports
```
Expected: No errors.

- [ ] **Step 4: Run existing pix smoke test**

```bash
cd backend && python -m pytest tests/test_pix_service_smoke.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/protocol.py \
        backend/finacialsim_saas/pix/fake.py
git commit -m "feat(inadimplencia): add multa_pct/juros_diario_pct/carencia_dias to PixProvider Protocol"
```

---

## Task 5: Extract `_ensure_charge` + Overdue Penalty Logic

**Files:**
- Modify: `backend/finacialsim_saas/pix/service.py`
- Create: `backend/tests/test_pix_service_inadimplencia.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/test_pix_service_inadimplencia.py`:

```python
"""Integration tests for _ensure_charge overdue regeneration logic."""
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    BusinessRule, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus,
    PixCharge, PixChargeStatus, Proposal, ProposalRenderStatus, ProposalStatus,
    Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings

UTC = timezone.utc


@pytest_asyncio.fixture
async def inad_setup(session: AsyncSession):
    """Tenant with multa 2%, juros 0.033%/day, carencia 0. Overdue parcela."""
    tenant = Tenant(name="InadSvc", slug=f"inad-svc-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    svc_auth = AuthService(session, get_settings())
    admin = await svc_auth.register_user(
        tenant_id=tenant.id, email=f"adm-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="Admin", role=Role.admin,
    )
    client = Client(
        tenant_id=tenant.id, nome="Bob", cpf_cnpj=f"000.{uuid.uuid4().int % 999:03d}.000-00",
        tipo=ClientType.pf, email=f"bob-{uuid.uuid4().hex[:6]}@example.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"SIM-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        valor_financiado=Decimal("40000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=1, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("42000"),
        total_pago=Decimal("42000"), total_juros=Decimal("2000"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"PROP-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7,
        snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    parcela = ParcelaPayment(
        tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=1,
        vencimento=date.today() - timedelta(days=5),
        valor_parcela=Decimal("1000"), status=ParcelaPaymentStatus.overdue,
    )
    session.add(parcela)
    await session.flush()

    # Configure penalty rules (valor_json stores the Python value; sa.JSON serializes correctly)
    for chave, valor in [
        ("inadimplencia_multa_pct",        "2.00"),
        ("inadimplencia_juros_diario_pct", "0.033"),
        ("inadimplencia_carencia_dias",    0),
    ]:
        session.add(BusinessRule(
            id=uuid.uuid4(), tenant_id=tenant.id,
            chave=chave, valor_json=valor, descricao="test",
        ))

    await session.commit()

    ctx = RequestContext(
        user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0,
    )
    storage = AsyncMock()
    storage.put = AsyncMock(return_value="pix/test/qr.png")
    storage.signed_url = AsyncMock(return_value="https://fake.url/qr.png")
    provider = InMemoryFakePixProvider()
    return {
        "tenant": tenant, "parcela": parcela, "ctx": ctx,
        "storage": storage, "provider": provider, "session": session,
    }


@pytest.mark.asyncio
async def test_stale_overdue_charge_is_regenerated(session: AsyncSession, inad_setup):
    """An overdue charge created yesterday is canceled and a new one created."""
    parcela = inad_setup["parcela"]
    storage = inad_setup["storage"]
    provider = inad_setup["provider"]
    ctx = inad_setup["ctx"]

    pix_svc = PixService(session, provider, storage)

    # First call: creates a charge
    charge1, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    assert charge1.status == PixChargeStatus.pending

    # Wind back criado_em to yesterday so it's stale
    charge1.criado_em = datetime(2020, 1, 1, tzinfo=UTC)
    await session.commit()

    # Second call: stale → regenerate
    charge2, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)

    await session.refresh(charge1)
    assert charge1.status == PixChargeStatus.canceled
    assert charge2.id != charge1.id
    assert charge2.status == PixChargeStatus.pending


@pytest.mark.asyncio
async def test_fresh_overdue_charge_not_regenerated(session: AsyncSession, inad_setup):
    """An overdue charge created today is returned as-is (no regeneration)."""
    parcela = inad_setup["parcela"]
    storage = inad_setup["storage"]
    provider = inad_setup["provider"]
    ctx = inad_setup["ctx"]

    pix_svc = PixService(session, provider, storage)

    charge1, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    charge2, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)

    assert charge1.id == charge2.id  # same charge, not regenerated


@pytest.mark.asyncio
async def test_overdue_within_carencia_not_regenerated(session: AsyncSession, inad_setup):
    """Within grace period, stale overdue charge is NOT regenerated."""
    parcela = inad_setup["parcela"]
    session_obj = inad_setup["session"]
    storage = inad_setup["storage"]
    provider = inad_setup["provider"]
    ctx = inad_setup["ctx"]
    tenant = inad_setup["tenant"]

    # Set carencia_dias = 10 (parcela is 5 days overdue, so within grace)
    from sqlalchemy import text, select as sa_select
    carencia_rule = await session_obj.scalar(
        sa_select(BusinessRule).where(
            BusinessRule.tenant_id == tenant.id,
            BusinessRule.chave == "inadimplencia_carencia_dias",
        )
    )
    carencia_rule.valor_json = 10
    await session_obj.commit()

    pix_svc = PixService(session, provider, storage)

    charge1, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    charge1.criado_em = datetime(2020, 1, 1, tzinfo=UTC)
    await session.commit()

    charge2, _ = await pix_svc.create_charge_for_parcela(parcela.id, ctx)
    assert charge1.id == charge2.id  # NOT regenerated — within carência
```

Run:
```bash
cd backend && python -m pytest tests/test_pix_service_inadimplencia.py -v
```
Expected: FAIL (import error or `_ensure_charge` not found).

- [ ] **Step 2: Refactor `service.py` — extract `_ensure_charge`, add BRT staleness + carência**

Replace the full content of `backend/finacialsim_saas/pix/service.py` with the following (the only changes are: (a) extract `_ensure_charge`, (b) add `_created_before_today_brt`, (c) add rules + penalty logic; `handle_webhook`, `get_charge`, `cancel_charges_for_proposal` are unchanged):

```python
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AuditLog, ParcelaPayment, ParcelaPaymentStatus, PixCharge,
    PixChargeStatus, PixWebhookEvent, Proposal, Role, Simulation, User,
)
from finacialsim_saas.errors import NotFoundError, ValidationError
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.storage import StorageBackend

UTC = timezone.utc
_BRT = ZoneInfo("America/Sao_Paulo")


def _created_before_today_brt(charge: PixCharge) -> bool:
    """True if the charge was created on a previous BRT calendar day."""
    created_brt = charge.criado_em.astimezone(_BRT).date()
    today_brt = datetime.now(_BRT).date()
    return created_brt < today_brt


class PixService:
    def __init__(
        self,
        session: AsyncSession,
        provider: PixProvider,
        storage: StorageBackend,
    ) -> None:
        self._s = session
        self._provider = provider
        self._storage = storage

    async def _lazy_flip_expired(self, charge: PixCharge) -> None:
        if (
            charge.status == PixChargeStatus.pending
            and charge.expires_at.replace(tzinfo=UTC) < datetime.now(UTC)
        ):
            charge.status = PixChargeStatus.expired
            charge.atualizado_em = datetime.now(UTC)

    async def _ensure_charge(
        self,
        parcela: ParcelaPayment,
    ) -> tuple[PixCharge, str]:
        """Idempotent charge creation with overdue regeneration.

        For open parcelas: returns existing pending charge or creates new one.
        For overdue parcelas past the grace period with non-zero rates: regenerates
        a stale charge (created before today BRT) so interest accrual is current.
        """
        from finacialsim_saas.services.rules_service import RulesService

        rules = await RulesService(self._s).get_rules(parcela.tenant_id)
        multa_pct_raw = Decimal(str(rules.get("inadimplencia_multa_pct", "0.00")))
        juros_pct_raw = Decimal(str(rules.get("inadimplencia_juros_diario_pct", "0.00")))
        carencia_dias = int(rules.get("inadimplencia_carencia_dias", 0))

        today = date.today()
        dias_atraso = (today - parcela.vencimento).days if parcela.vencimento < today else 0
        rates_past_grace = (
            parcela.status == ParcelaPaymentStatus.overdue
            and dias_atraso > carencia_dias
            and (multa_pct_raw > 0 or juros_pct_raw > 0)
        )
        multa_pct = multa_pct_raw if rates_past_grace else Decimal("0.00")
        juros_diario_pct = juros_pct_raw if rates_past_grace else Decimal("0.00")

        # Check for existing pending charge
        if parcela.last_pix_charge_id is not None:
            existing = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if existing is not None:
                await self._lazy_flip_expired(existing)
                if existing.status == PixChargeStatus.pending:
                    needs_regeneration = (
                        rates_past_grace and _created_before_today_brt(existing)
                    )
                    if not needs_regeneration:
                        await self._s.flush()
                        qr_url = await self._storage.signed_url(
                            existing.qrcode_png_key, expires_in=1800
                        )
                        return existing, qr_url
                    # Cancel stale charge
                    try:
                        await self._provider.cancel_charge(existing.txid)
                    except Exception:
                        pass
                    existing.status = PixChargeStatus.canceled
                    existing.atualizado_em = datetime.now(UTC)

        # Create new charge
        charge_id = uuid.uuid4()
        txid = str(charge_id).replace("-", "")[:35]

        charge_data = await self._provider.create_charge(
            txid=txid,
            amount=parcela.valor_parcela,
            expires_in=1800,
            description=f"Parcela {parcela.parcela_num}",
            payer="",
            multa_pct=multa_pct,
            juros_diario_pct=juros_diario_pct,
            carencia_dias=carencia_dias,
        )

        qr_key = f"pix/{charge_id}/qr.png"
        await self._storage.put(qr_key, charge_data.qr_png_bytes, "image/png")

        now = datetime.now(UTC)
        charge = PixCharge(
            id=charge_id,
            tenant_id=parcela.tenant_id,
            parcela_payment_id=parcela.id,
            txid=txid,
            brcode=charge_data.brcode,
            qrcode_png_key=qr_key,
            amount=charge_data.amount,
            expires_at=charge_data.expires_at,
            status=PixChargeStatus.pending,
            provider_payload_json=charge_data.provider_payload,
            criado_em=now,
            atualizado_em=now,
        )
        self._s.add(charge)
        parcela.last_pix_charge_id = charge_id
        await self._s.flush()

        return charge, await self._storage.signed_url(qr_key, expires_in=1800)

    async def create_charge_for_parcela(
        self, parcela_payment_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Idempotent. Returns (charge, signed_qr_url). TTL 30 min."""
        parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
        if parcela is None or parcela.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if ctx.client_id is not None:
            proposal = await self._s.get(Proposal, parcela.proposal_id)
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"parcela payment {parcela_payment_id} not found")

        if parcela.status not in (ParcelaPaymentStatus.open, ParcelaPaymentStatus.overdue):
            raise ValidationError("parcela must be open or overdue to pay")

        charge, qr_url = await self._ensure_charge(parcela)
        await self._s.commit()

        # Notify customer: Pix link available
        try:
            from finacialsim_saas.notifications.service import NotificationService
            proposal_obj = await self._s.get(Proposal, parcela.proposal_id)
            if proposal_obj is not None:
                sim_obj = await self._s.get(Simulation, proposal_obj.simulation_id)
                if sim_obj is not None and sim_obj.client_id is not None:
                    cu_result = await self._s.execute(
                        select(User).where(
                            User.client_id == sim_obj.client_id,
                            User.role == Role.customer,
                            User.is_active.is_(True),
                        )
                    )
                    customer = cu_result.scalar_one_or_none()
                    if customer and "@" in (customer.email or ""):
                        pix_url = await self._storage.signed_url(
                            charge.qrcode_png_key, expires_in=1800
                        )
                        await NotificationService(self._s).enqueue(
                            template_key="portal.pix_link",
                            payload={
                                "user_name": customer.name,
                                "valor_parcela": str(parcela.valor_parcela),
                                "parcela_num": parcela.parcela_num,
                                "pix_url": pix_url,
                            },
                            target_email=customer.email,
                            tenant_id=ctx.tenant_id,
                            idempotency_key=f"portal.pix_link:{parcela_payment_id}",
                        )
        except Exception as exc:
            logger.warning("pix_link notification failed", exc=str(exc))

        return charge, qr_url

    async def handle_webhook(self, headers: dict[str, str], body: bytes) -> None:
        """Logs every payload. Verifies HMAC. Processes paid events idempotently."""
        now = datetime.now(UTC)

        try:
            body_json: dict[str, Any] = json.loads(body)
        except Exception:
            body_json = {"_raw": body.decode("utf-8", errors="replace")[:500]}

        try:
            event = self._provider.verify_webhook(headers, body)
            signature_valid = True
        except Exception as exc:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=False,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error=str(exc)[:200],
                )
            )
            await self._s.commit()
            return

        if event.status != "paid":
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error=f"unhandled status: {event.status}",
                )
            )
            await self._s.commit()
            return

        charge_result = await self._s.execute(
            select(PixCharge).where(PixCharge.txid == event.txid)
        )
        charge = charge_result.scalar_one_or_none()

        if charge is None:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error="charge not found",
                )
            )
            await self._s.commit()
            return

        if charge.status == PixChargeStatus.paid:
            self._s.add(
                PixWebhookEvent(
                    received_at=now,
                    signature_valid=True,
                    headers_json=dict(headers),
                    body_json=body_json,
                    processed=False,
                    error="already processed (replay)",
                )
            )
            await self._s.commit()
            return

        charge.status = PixChargeStatus.paid
        charge.atualizado_em = now

        parcela = await self._s.get(ParcelaPayment, charge.parcela_payment_id)
        if parcela is not None:
            parcela.status = ParcelaPaymentStatus.paid
            parcela.paid_at = now
            parcela.paid_amount = event.paid_amount or charge.amount
            parcela.last_pix_charge_id = charge.id

        self._s.add(
            AuditLog(
                tenant_id=charge.tenant_id,
                acao="parcela_paga",
                entidade="parcela_payments",
                entidade_id=charge.parcela_payment_id,
                diff_json={
                    "txid": event.txid,
                    "amount": str(event.paid_amount or charge.amount),
                },
            )
        )
        self._s.add(
            PixWebhookEvent(
                received_at=now,
                signature_valid=True,
                headers_json=dict(headers),
                body_json=body_json,
                processed=True,
                processed_at=now,
            )
        )

        if parcela is not None:
            try:
                from finacialsim_saas.notifications.service import NotificationService
                proposal_obj = await self._s.get(Proposal, parcela.proposal_id)
                if proposal_obj is not None:
                    sim_obj = await self._s.get(Simulation, proposal_obj.simulation_id)
                    if sim_obj is not None and sim_obj.client_id is not None:
                        cu_result = await self._s.execute(
                            select(User).where(
                                User.client_id == sim_obj.client_id,
                                User.role == Role.customer,
                            )
                        )
                        customer = cu_result.scalar_one_or_none()
                        if customer and "@" in (customer.email or ""):
                            await NotificationService(self._s).enqueue(
                                template_key="portal.parcela_paid",
                                payload={
                                    "user_name": customer.name,
                                    "valor_pago": str(parcela.paid_amount or charge.amount),
                                    "parcela_num": parcela.parcela_num,
                                },
                                target_email=customer.email,
                                tenant_id=parcela.tenant_id,
                                idempotency_key=f"portal.parcela_paid:{parcela.id}",
                            )
            except Exception as exc:
                logger.warning("parcela_paid notification failed", exc=str(exc))

        await self._s.commit()

    async def get_charge(
        self, charge_id: uuid.UUID, ctx: RequestContext
    ) -> tuple[PixCharge, str]:
        """Lazy-flips expiry, returns charge + signed QR URL."""
        charge = await self._s.get(PixCharge, charge_id)
        if charge is None or charge.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"pix charge {charge_id} not found")

        if ctx.client_id is not None:
            parcela = await self._s.get(ParcelaPayment, charge.parcela_payment_id)
            proposal = await self._s.get(Proposal, parcela.proposal_id) if parcela else None
            sim = await self._s.get(Simulation, proposal.simulation_id) if proposal else None
            if sim is None or sim.client_id != ctx.client_id:
                raise NotFoundError(f"pix charge {charge_id} not found")

        await self._lazy_flip_expired(charge)
        if charge.status == PixChargeStatus.expired:
            await self._s.commit()

        qr_url = await self._storage.signed_url(charge.qrcode_png_key, expires_in=1800)
        return charge, qr_url

    async def cancel_charges_for_proposal(self, proposal_id: uuid.UUID) -> None:
        """Cancel all pending charges for all parcelas of a proposal."""
        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment).where(
                    ParcelaPayment.proposal_id == proposal_id,
                    ParcelaPayment.last_pix_charge_id.isnot(None),
                )
            )
        )
        now = datetime.now(UTC)
        for parcela in parcelas:
            charge = await self._s.get(PixCharge, parcela.last_pix_charge_id)
            if charge is not None and charge.status == PixChargeStatus.pending:
                try:
                    await self._provider.cancel_charge(charge.txid)
                except Exception:
                    pass
                charge.status = PixChargeStatus.canceled
                charge.atualizado_em = now
        await self._s.flush()
```

- [ ] **Step 3: Run integration tests**

```bash
cd backend && python -m pytest tests/test_pix_service_inadimplencia.py -v
```
Expected: all 3 tests pass.

- [ ] **Step 4: Run existing pix smoke test to check no regression**

```bash
cd backend && python -m pytest tests/test_pix_service_smoke.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/pix/service.py \
        backend/tests/test_pix_service_inadimplencia.py
git commit -m "feat(inadimplencia): extract _ensure_charge, add carencia gate + daily regeneration"
```

---

## Task 6: `_calculate_overdue_amount` + Portal Enrichment

**Files:**
- Modify: `backend/finacialsim_saas/services/parcela_service.py`
- Modify: `backend/finacialsim_saas/api/portal.py`
- Create: `backend/tests/test_inadimplencia_overdue_amount.py`

- [ ] **Step 1: Write unit tests for `_calculate_overdue_amount`**

Create `backend/tests/test_inadimplencia_overdue_amount.py`:

```python
from decimal import Decimal
import pytest

from finacialsim_saas.services.parcela_service import _calculate_overdue_amount


def test_within_carencia_returns_zero_encargos():
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=2,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=3,
    )
    assert result["multa"] == "0.00"
    assert result["juros_acumulado"] == "0.00"
    assert result["valor_corrigido"] == "1000.00"
    assert result["estimativa"] is True


def test_day_1_past_carencia_applies_multa_and_juros():
    """Day 1 past carência: 1 day of juros + multa applied."""
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=1,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=0,
    )
    assert result["multa"] == "20.00"       # 2% of 1000
    assert result["juros_acumulado"] == "0.33"  # 0.033% * 1 day * 1000
    assert result["valor_corrigido"] == "1020.33"


def test_five_days_overdue_no_carencia():
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=5,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=0,
    )
    assert result["multa"] == "20.00"
    assert result["juros_acumulado"] == "1.65"   # 0.033% * 5 * 1000
    assert result["valor_corrigido"] == "1021.65"
    assert result["dias_atraso"] == 5


def test_five_days_overdue_carencia_two():
    """5 days overdue, 2 days grace → 3 dias_com_encargos."""
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=5,
        multa_pct=Decimal("2.0"),
        juros_diario_pct=Decimal("0.033"),
        carencia_dias=2,
    )
    assert result["multa"] == "20.00"
    assert result["juros_acumulado"] == "0.99"   # 0.033% * 3 * 1000
    assert result["valor_corrigido"] == "1020.99"


def test_zero_rates_returns_original_value():
    result = _calculate_overdue_amount(
        valor_parcela=Decimal("1000"),
        dias_atraso=10,
        multa_pct=Decimal("0.00"),
        juros_diario_pct=Decimal("0.00"),
        carencia_dias=0,
    )
    assert result["multa"] == "0.00"
    assert result["juros_acumulado"] == "0.00"
    assert result["valor_corrigido"] == "1000.00"
```

Run:
```bash
cd backend && python -m pytest tests/test_inadimplencia_overdue_amount.py -v
```
Expected: all 5 tests fail (function not yet defined).

- [ ] **Step 2: Add `_calculate_overdue_amount` to `parcela_service.py`**

Add the import `from decimal import Decimal` to the top of `parcela_service.py` if not present.

Add this module-level function after the existing `_effective_status` function (around line 36):

```python
def _calculate_overdue_amount(
    valor_parcela: Decimal,
    dias_atraso: int,
    multa_pct: Decimal,
    juros_diario_pct: Decimal,
    carencia_dias: int,
) -> dict:
    """Pure function: computes real-time encargos estimate for an overdue parcela."""
    dias_com_encargos = max(dias_atraso - carencia_dias, 0)
    if dias_com_encargos > 0:
        multa = (valor_parcela * multa_pct / 100).quantize(Decimal("0.01"))
    else:
        multa = Decimal("0.00")
    juros = (valor_parcela * juros_diario_pct / 100 * dias_com_encargos).quantize(Decimal("0.01"))
    valor_corrigido = valor_parcela + multa + juros
    return {
        "multa": str(multa),
        "juros_acumulado": str(juros),
        "valor_corrigido": str(valor_corrigido),
        "dias_atraso": dias_atraso,
        "estimativa": True,
    }
```

- [ ] **Step 3: Run unit tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_inadimplencia_overdue_amount.py -v
```
Expected: all 5 tests pass.

- [ ] **Step 4: Update `get_schedule()` to enrich overdue parcelas**

In `parcela_service.py`, update `get_schedule()` to read rules and add `encargos` for overdue parcelas. Replace the body of `get_schedule` from `parcelas = list(...)` onward:

```python
    async def get_schedule(
        self, proposal_id: uuid.UUID, ctx: RequestContext
    ) -> dict[str, Any]:
        """Returns full parcela schedule; verifies customer ownership."""
        if ctx.client_id is None:
            raise NotFoundError(f"proposal {proposal_id} not found")

        proposal = await self._s.get(Proposal, proposal_id)
        if proposal is None or proposal.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"proposal {proposal_id} not found")

        sim = await self._s.get(Simulation, proposal.simulation_id)
        if sim is None or sim.client_id != ctx.client_id:
            raise NotFoundError(f"proposal {proposal_id} not found")

        parcelas = list(
            await self._s.scalars(
                select(ParcelaPayment)
                .where(ParcelaPayment.proposal_id == proposal_id)
                .order_by(ParcelaPayment.parcela_num)
            )
        )

        from finacialsim_saas.services.rules_service import RulesService
        rules = await RulesService(self._s).get_rules(proposal.tenant_id)
        multa_pct = Decimal(str(rules.get("inadimplencia_multa_pct", "0.00")))
        juros_diario_pct = Decimal(str(rules.get("inadimplencia_juros_diario_pct", "0.00")))
        carencia_dias = int(rules.get("inadimplencia_carencia_dias", 0))

        today = date.today()
        next_open_id = None
        parcela_list = []
        for p in parcelas:
            status = _effective_status(p)
            if next_open_id is None and status in ("open", "overdue"):
                next_open_id = str(p.id)
            item: dict[str, Any] = {
                "id": str(p.id),
                "parcela_num": p.parcela_num,
                "vencimento": p.vencimento.isoformat(),
                "valor_parcela": str(p.valor_parcela),
                "status": status,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                "paid_amount": str(p.paid_amount) if p.paid_amount else None,
            }
            if status == "overdue":
                dias_atraso = (today - p.vencimento).days
                item["encargos"] = _calculate_overdue_amount(
                    p.valor_parcela, dias_atraso, multa_pct, juros_diario_pct, carencia_dias
                )
            parcela_list.append(item)

        return {
            "proposal_id": str(proposal.id),
            "codigo": proposal.codigo,
            "veiculo": _vehicle_desc(proposal.snapshot_json),
            "next_open_parcela_id": next_open_id,
            "parcelas": parcela_list,
        }
```

Add `from decimal import Decimal` to the top-level imports of `parcela_service.py` if not already present.

- [ ] **Step 5: Update `portal.py` `get_parcela` endpoint**

In `backend/finacialsim_saas/api/portal.py`, update the `get_parcela` endpoint to use `_effective_status` and add `encargos`:

```python
@router.get("/parcelas/{parcela_id}")
async def get_parcela(
    parcela_id: uuid.UUID,
    ctx: _CustomerCtx,
    session: _Session,
) -> dict:
    from datetime import date
    from decimal import Decimal
    from finacialsim_saas.services.parcela_service import _calculate_overdue_amount, _effective_status
    from finacialsim_saas.services.rules_service import RulesService

    svc = _parcela_svc(session)
    p = await svc.get_parcela(parcela_id, ctx)
    effective = _effective_status(p)
    resp: dict = {
        "id": str(p.id),
        "parcela_num": p.parcela_num,
        "vencimento": p.vencimento.isoformat(),
        "valor_parcela": str(p.valor_parcela),
        "status": effective,
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        "paid_amount": str(p.paid_amount) if p.paid_amount else None,
    }
    if effective == "overdue":
        rules = await RulesService(session).get_rules(ctx.tenant_id)
        dias_atraso = (date.today() - p.vencimento).days
        resp["encargos"] = _calculate_overdue_amount(
            p.valor_parcela,
            dias_atraso,
            Decimal(str(rules.get("inadimplencia_multa_pct", "0.00"))),
            Decimal(str(rules.get("inadimplencia_juros_diario_pct", "0.00"))),
            int(rules.get("inadimplencia_carencia_dias", 0)),
        )
    return resp
```

- [ ] **Step 6: Write integration test for `get_schedule` encargos**

Append to `backend/tests/test_inadimplencia_overdue_amount.py`:

```python
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import (
    BusinessRule, Client, ClientType, ParcelaPayment, ParcelaPaymentStatus,
    Proposal, ProposalRenderStatus, ProposalStatus, Role, Simulation, SimulationStatus, Tenant,
)
from finacialsim_saas.services.parcela_service import ParcelaService
from finacialsim_saas.settings import get_settings


@pytest_asyncio.fixture
async def overdue_schedule_setup(session: AsyncSession):
    from sqlalchemy import text

    tenant = Tenant(name="OvdSched", slug=f"ovd-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()

    svc = AuthService(session, get_settings())
    admin = await svc.register_user(
        tenant_id=tenant.id, email=f"a-{uuid.uuid4().hex[:6]}@t.com",
        password="x", name="A", role=Role.admin,
    )
    client = Client(
        tenant_id=tenant.id, nome="C", cpf_cnpj=f"111.{uuid.uuid4().int % 999:03d}.111-11",
        tipo=ClientType.pf, email=f"c-{uuid.uuid4().hex[:6]}@t.com", criado_por=admin.id,
    )
    session.add(client)
    await session.flush()

    sim = Simulation(
        tenant_id=tenant.id, codigo=f"S-{uuid.uuid4().hex[:6]}",
        valor_veiculo=Decimal("10000"), valor_entrada=Decimal("1000"),
        valor_financiado=Decimal("9000"), taxa_mensal=Decimal("0.02"),
        prazo_meses=1, data_liberacao=date.today(), primeiro_vencimento=date.today(),
        incluir_iof=False, iof_total=Decimal("0"), parcela_financiamento=Decimal("9180"),
        total_pago=Decimal("9180"), total_juros=Decimal("180"),
        cet_mensal=Decimal("0.021"), cet_anual=Decimal("0.28"),
        status=SimulationStatus.confirmado, rules_snapshot_json={},
        client_id=client.id, vehicle_id=None, criado_por=admin.id,
    )
    session.add(sim)
    await session.flush()

    proposal = Proposal(
        tenant_id=tenant.id, simulation_id=sim.id,
        codigo=f"P-{uuid.uuid4().hex[:6]}", gerado_por=admin.id,
        validade_dias=7,
        snapshot_json={"sim": {}, "cronograma": [], "loja": {}, "vendedor": {}, "cliente": None, "veiculo": None},
        render_status=ProposalRenderStatus.ready, status=ProposalStatus.aprovada,
    )
    session.add(proposal)
    await session.flush()

    overdue_parcela = ParcelaPayment(
        tenant_id=tenant.id, proposal_id=proposal.id, parcela_num=1,
        vencimento=date.today() - timedelta(days=3),
        valor_parcela=Decimal("1000"), status=ParcelaPaymentStatus.overdue,
    )
    session.add(overdue_parcela)
    await session.flush()

    # Set 2% multa, 0.033%/day juros, 0 carencia
    for chave, val in [
        ("inadimplencia_multa_pct",        "2.00"),
        ("inadimplencia_juros_diario_pct", "0.033"),
        ("inadimplencia_carencia_dias",    0),
    ]:
        session.add(BusinessRule(
            id=uuid.uuid4(), tenant_id=tenant.id,
            chave=chave, valor_json=val, descricao="test",
        ))

    await session.commit()

    customer_user = await svc.invite_customer(client.id, RequestContext(
        user_id=admin.id, tenant_id=tenant.id, role=Role.admin, iat=0.0,
    ))
    await session.commit()

    return {
        "tenant": tenant, "proposal": proposal, "client": client,
        "customer_user": customer_user,
    }


@pytest.mark.asyncio
async def test_get_schedule_includes_encargos_for_overdue(session, overdue_schedule_setup):
    d = overdue_schedule_setup
    ctx = RequestContext(
        user_id=d["customer_user"].id, tenant_id=d["tenant"].id,
        role=Role.customer, iat=0.0, client_id=d["client"].id,
    )
    svc = ParcelaService(session)
    schedule = await svc.get_schedule(d["proposal"].id, ctx)

    overdue_item = next(p for p in schedule["parcelas"] if p["status"] == "overdue")
    assert "encargos" in overdue_item
    enc = overdue_item["encargos"]
    assert enc["multa"] == "20.00"           # 2% of 1000
    assert enc["estimativa"] is True
    assert float(enc["juros_acumulado"]) > 0


@pytest.mark.asyncio
async def test_get_schedule_open_parcela_has_no_encargos(session, overdue_schedule_setup):
    """Future (open) parcelas should not have encargos key."""
    d = overdue_schedule_setup
    ctx = RequestContext(
        user_id=d["customer_user"].id, tenant_id=d["tenant"].id,
        role=Role.customer, iat=0.0, client_id=d["client"].id,
    )

    from sqlalchemy import text
    from finacialsim_saas.data.models import ParcelaPayment, ParcelaPaymentStatus
    future_p = ParcelaPayment(
        tenant_id=d["tenant"].id, proposal_id=d["proposal"].id, parcela_num=2,
        vencimento=date.today() + timedelta(days=30),
        valor_parcela=Decimal("1000"), status=ParcelaPaymentStatus.open,
    )
    session.add(future_p)
    await session.commit()

    svc = ParcelaService(session)
    schedule = await svc.get_schedule(d["proposal"].id, ctx)
    open_item = next(p for p in schedule["parcelas"] if p["status"] == "open")
    assert "encargos" not in open_item
```

- [ ] **Step 7: Run all new tests**

```bash
cd backend && python -m pytest tests/test_inadimplencia_overdue_amount.py -v
```
Expected: all tests pass.

- [ ] **Step 8: Run the full test suite to check no regressions**

```bash
cd backend && python -m pytest tests/ -v --timeout=120
```
Expected: all pass (or any pre-existing failures are unchanged).

- [ ] **Step 9: Commit**

```bash
git add backend/finacialsim_saas/services/parcela_service.py \
        backend/finacialsim_saas/api/portal.py \
        backend/tests/test_inadimplencia_overdue_amount.py
git commit -m "feat(inadimplencia): add encargos estimate to get_schedule and portal get_parcela"
```

---

## Acceptance Checklist

Run after all 6 tasks are complete:

```bash
cd backend && python -m pytest tests/test_inadimplencia_rules.py \
    tests/test_pix_service_inadimplencia.py \
    tests/test_inadimplencia_overdue_amount.py -v
```

All should pass. Then run:

```bash
cd backend && python -m pytest tests/ -v --timeout=120
```

Full suite must be green (or no new failures vs pre-existing baseline).

**Manual smoke via API:**
1. `PUT /api/v1/business-rules/inadimplencia_multa_pct {"valor": "2.00"}` → 204
2. `PUT /api/v1/business-rules/inadimplencia_multa_pct {"valor": "2.01"}` → 422
3. `GET /api/v1/business-rules` → includes `inadimplencia_multa_pct: "2.00"`
4. Create an overdue parcela + call `POST /api/v1/portal/parcelas/{id}/pix-charge` twice — second call returns same charge (not regenerated, created same day)
5. `GET /api/v1/portal/financiamentos/{proposal_id}` with overdue parcelas → `encargos` key present

---

## Notes for Phase 1 Integration

When Phase 1 (EfiPixProvider) is implemented, `EfiPixProvider.create_charge` must:
- Accept `multa_pct`, `juros_diario_pct`, `carencia_dias` (per updated Protocol)
- Build the CobV body with:
  ```python
  body["multa"] = {"modalidade": 2, "valorPerc": str(multa_pct)}
  body["juros"] = {"modalidade": 2, "valorPerc": str(juros_diario_pct)}
  ```
- `carencia_dias` is NOT passed to the CobV body — the BACEN schema has no `dataInicio` field on multa/juros. The carência gate is handled at `_ensure_charge` level (Task 5).
- Change `expires_in: int` → `due_date: date, validity_days: int` (separate Phase 1 Protocol change)
- `modalidade: 2` = "Percentual ao dia (dias corridos)" for juros; `modalidade: 2` = "Percentual" for multa
