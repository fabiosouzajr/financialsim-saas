# Phase 4 Backend — Indicadores + Business Rules + Scheduler + Audit Log

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring SELIC/CDI/IPCA/TX_BACEN_VEIC indicators online via daily ARQ job, add admin-only business rule update endpoint with Redis invalidation, wire `audit_service.log()` into every CUD service path, and expose a paginated audit log API.

**Architecture:** New `integrations/bacen/` directory under backend holds pure HTTP providers (SGS primary, BrasilAPI fallback). `IndicatorsService` and `AuditService` follow the existing service pattern (async SQLAlchemy session injected in constructor). Three ARQ cron jobs scheduled in `WorkerSettings`. Audit log uses keyset cursor pagination on `(tenant_id, timestamp DESC)`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, ARQ cron, asyncpg, respx (test HTTP mocking), redis.asyncio (pub/sub), testcontainers Redis+Postgres

---

## Decisions baked into this plan

| Topic | Decision |
|---|---|
| Scheduled job audit entries | None — global job doesn't write per-tenant audit rows |
| ARQ lock key | `lock:{job_name}:{YYYY-MM-DD}` |
| Stale thresholds | SELIC/CDI=26h, IPCA/TX_BACEN_VEIC=744h |
| Redis → frontend | React Query polling only (no WebSocket) |
| `provider_health` retention | Last 50 rows per provider_name |
| `indicators/refresh` endpoint | `POST /api/v1/indicators/refresh` (admin, 202) |
| `taxa_por_prazo_curva` editor | Frontend dynamic row table (Phase 4 frontend plan) |
| `diff_json` format | `{"before": {...}, "after": {...}}` |
| Audit scope | All CUD + `register_user` + simulation status changes |
| GET /business-rules access | Open to all staff (unchanged) |
| `motivo` | Optional in PUT body; stored inside `diff_json` |
| Series range | `Nm` strings: 3m/6m/12m/24m, default 12m |
| Cursor | Keyset base64(`{"ts": ..., "id": ...}`) |
| Indicators response | Array |
| Provider health providers | fipe_parallelum, fipe_brasilapi, bacen_sgs, bacen_brasilapi |
| BACEN location | `backend/finacialsim_saas/integrations/bacen/` |
| SELIC codigo | SGS 432, `pct_aa`, annual rate |
| TX_BACEN_VEIC fallback | None — stale row persists on SGS failure |
| `indicators_history.valor` | Percentage (10.75, not 0.1075) |
| date filter | `date_from` / `date_to` ISO params |
| Page size | 20 |

---

## File Map

**Create:**
- `backend/alembic/versions/005_indicators_provider_health.py`
- `backend/finacialsim_saas/integrations/__init__.py`
- `backend/finacialsim_saas/integrations/bacen/__init__.py`
- `backend/finacialsim_saas/integrations/bacen/schema.py`
- `backend/finacialsim_saas/integrations/bacen/sgs.py`
- `backend/finacialsim_saas/integrations/bacen/brasilapi.py`
- `backend/finacialsim_saas/services/indicators_service.py`
- `backend/finacialsim_saas/services/audit_service.py`
- `backend/finacialsim_saas/schemas/indicators.py`
- `backend/finacialsim_saas/schemas/audit_log.py`
- `backend/finacialsim_saas/api/indicators.py`
- `backend/finacialsim_saas/api/audit_log.py`
- `backend/tests/test_bacen_providers.py`
- `backend/tests/test_indicators_service.py`
- `backend/tests/test_audit_service.py`
- `backend/tests/test_rules_update.py`
- `backend/tests/test_arq_jobs.py`
- `backend/tests/test_indicators_endpoints.py`
- `backend/tests/test_audit_log_endpoints.py`
- `backend/tests/test_audit_backfill.py`

**Modify:**
- `backend/finacialsim_saas/data/models.py` — add `IndicatorHistory`, `ProviderHealth`
- `backend/finacialsim_saas/services/rules_service.py` — add `update()`
- `backend/finacialsim_saas/api/business_rules.py` — add `PUT /business-rules/{chave}`
- `backend/finacialsim_saas/schemas/business_rules.py` — add `BusinessRuleUpdateIn`
- `backend/finacialsim_saas/main.py` — Redis client in lifespan, register new routers
- `backend/finacialsim_saas/workers/tasks.py` — add 3 job functions
- `backend/finacialsim_saas/workers/worker.py` — add cron jobs, on_startup/shutdown
- `backend/finacialsim_saas/auth/service.py` — audit on `register_user`
- `backend/finacialsim_saas/services/client_service.py` — audit on create/update/deactivate
- `backend/finacialsim_saas/services/vehicle_service.py` — audit on create/update/set_status
- `backend/finacialsim_saas/services/simulation_service.py` — audit on create/status change
- `backend/tests/test_models.py` — add phase 4 model test

---

## Task 1: DB Models + Migration

**Files:**
- Create: `backend/finacialsim_saas/data/models.py` (add 2 models)
- Create: `backend/alembic/versions/005_indicators_provider_health.py`
- Modify: `backend/tests/test_models.py`

- [ ] **Step 1: Add models to `models.py`**

Append after the `FipeCache` class:

```python
class IndicatorHistory(Base):
    __tablename__ = "indicators_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    codigo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    data_referencia: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    unidade: Mapped[str] = mapped_column(sa.Text, nullable=False)
    fonte: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    coletado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "codigo", "data_referencia", name="uq_indicators_history_codigo_date"
        ),
    )


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    provider_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    success: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_provider_health_name_checked", "provider_name", "checked_at"),
    )
```

- [ ] **Step 2: Write failing model test**

In `backend/tests/test_models.py`, add:

```python
async def test_all_phase4_models_importable_and_tables_exist(engine):
    from finacialsim_saas.data.models import IndicatorHistory, ProviderHealth
    from sqlalchemy import inspect, text

    async with engine.connect() as conn:
        tables = await conn.run_sync(
            lambda c: inspect(c).get_table_names()
        )
    assert "indicators_history" in tables
    assert "provider_health" in tables
```

- [ ] **Step 3: Run to verify it fails**

```bash
cd backend && uv run pytest tests/test_models.py::test_all_phase4_models_importable_and_tables_exist -v
```
Expected: FAIL — `indicators_history` not in tables.

- [ ] **Step 4: Create migration `005_indicators_provider_health.py`**

```python
"""indicators_history and provider_health tables"""
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
    op.drop_table("provider_health")
    op.drop_table("indicators_history")
```

Note: check the `down_revision` value matches whatever `004` migration file is named in your `alembic/versions/`. Look at the existing files to confirm the `revision` string used in `004_cadastros.py`.

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_models.py::test_all_phase4_models_importable_and_tables_exist -v
```
Expected: PASS (conftest creates tables via `Base.metadata.create_all`).

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/data/models.py \
        backend/alembic/versions/005_indicators_provider_health.py \
        backend/tests/test_models.py
git commit -m "feat(phase4): add IndicatorHistory and ProviderHealth models + migration 005"
```

---

## Task 2: BACEN Integration

**Files:**
- Create: `backend/finacialsim_saas/integrations/__init__.py`
- Create: `backend/finacialsim_saas/integrations/bacen/__init__.py`
- Create: `backend/finacialsim_saas/integrations/bacen/schema.py`
- Create: `backend/finacialsim_saas/integrations/bacen/sgs.py`
- Create: `backend/finacialsim_saas/integrations/bacen/brasilapi.py`
- Create: `backend/tests/test_bacen_providers.py`

- [ ] **Step 1: Write failing provider tests**

Create `backend/tests/test_bacen_providers.py`:

```python
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from finacialsim_core.integrations.base import ProviderChain
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.integrations.bacen.brasilapi import BrasilApiBacenProvider


@respx.mock
async def test_sgs_primary_ok():
    respx.get(
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
    ).mock(
        return_value=httpx.Response(200, json=[{"data": "01/06/2026", "valor": "10.75"}])
    )
    provider = BcbSgsProvider()
    result = await provider.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_ok
    assert len(result.value) == 1
    assert result.value[0].valor == Decimal("10.75")
    assert result.value[0].codigo == "SELIC"
    assert result.value[0].unidade == "pct_aa"


@respx.mock
async def test_sgs_http_error_returns_err():
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    provider = BcbSgsProvider()
    result = await provider.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_err


@respx.mock
async def test_chain_primary_fail_brasilapi_fallback():
    # SGS fails
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    # BrasilAPI succeeds
    respx.get("https://brasilapi.com.br/api/taxas/v1/Selic").mock(
        return_value=httpx.Response(200, json={"nome": "Selic", "valor": 10.75})
    )
    chain = ProviderChain([BcbSgsProvider(), BrasilApiBacenProvider()])
    result = await chain.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_ok
    assert result.value[0].valor == Decimal("10.75")


@respx.mock
async def test_chain_both_fail_returns_err():
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    respx.get("https://brasilapi.com.br/api/taxas/v1/Selic").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    chain = ProviderChain([BcbSgsProvider(), BrasilApiBacenProvider()])
    result = await chain.fetch({
        "codigo": "SELIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_err


@respx.mock
async def test_tx_bacen_veic_no_brasilapi_fallback():
    # SGS fails for TX_BACEN_VEIC
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.20714/dados").mock(
        side_effect=httpx.ConnectError("timeout")
    )
    # BrasilAPI returns Err for unsupported codigo — no HTTP call needed
    chain = ProviderChain([BcbSgsProvider(), BrasilApiBacenProvider()])
    result = await chain.fetch({
        "codigo": "TX_BACEN_VEIC",
        "data_inicial": date(2026, 6, 1),
        "data_final": date(2026, 6, 1),
    })
    assert result.is_err
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd backend && uv run pytest tests/test_bacen_providers.py -v
```
Expected: ImportError — `finacialsim_saas.integrations.bacen` not found.

- [ ] **Step 3: Create `integrations/__init__.py` and `integrations/bacen/__init__.py`**

```bash
touch backend/finacialsim_saas/integrations/__init__.py
touch backend/finacialsim_saas/integrations/bacen/__init__.py
```

- [ ] **Step 4: Create `integrations/bacen/schema.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Unidade = Literal["pct_aa", "pct_am", "pct_ad"]


@dataclass(frozen=True)
class IndicatorPoint:
    codigo: str
    data_referencia: date
    valor: Decimal  # percentage, e.g. 10.75 for 10.75% a.a.
    unidade: Unidade
    fonte: str
```

- [ ] **Step 5: Create `integrations/bacen/sgs.py`**

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.http import get_json, http_err_callback
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint, Unidade

BASE_URL = "https://api.bcb.gov.br/dados/serie"

# Maps our codigo → (SGS series number, unidade)
CODIGOS: dict[str, tuple[int, Unidade]] = {
    "SELIC": (432, "pct_aa"),
    "CDI": (12, "pct_ad"),
    "IPCA": (433, "pct_am"),
    "TX_BACEN_VEIC": (20714, "pct_am"),
}


class BcbSgsProvider:
    name = "bacen_sgs"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        if codigo not in CODIGOS:
            return Err(f"unknown_codigo: {codigo}")
        sgs_code, unidade = CODIGOS[codigo]
        di: date = query["data_inicial"]
        df: date = query["data_final"]
        url = (
            f"{BASE_URL}/bcdata.sgs.{sgs_code}/dados"
            f"?formato=json"
            f"&dataInicial={di.strftime('%d/%m/%Y')}"
            f"&dataFinal={df.strftime('%d/%m/%Y')}"
        )
        try:
            raw = await get_json(url, self._client)
            if not isinstance(raw, list):
                return Err(f"unexpected_response: {type(raw).__name__}")
            points: list[IndicatorPoint] = []
            for entry in raw:
                d_parts = entry["data"].split("/")
                ref_date = date(int(d_parts[2]), int(d_parts[1]), int(d_parts[0]))
                valor = Decimal(entry["valor"])
                if valor < 0 or valor > 100:
                    return Err(f"invalid_value_out_of_range: {valor}")
                points.append(IndicatorPoint(
                    codigo=codigo,
                    data_referencia=ref_date,
                    valor=valor,
                    unidade=unidade,
                    fonte="bacen_sgs",
                ))
            return Ok(points)
        except httpx.HTTPError:
            raise  # tenacity retries
        except (KeyError, ValueError, IndexError, TypeError) as e:
            return Err(f"parse_error: {e}")
```

- [ ] **Step 6: Create `integrations/bacen/brasilapi.py`**

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.http import get_json, http_err_callback
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint

BASE_URL = "https://brasilapi.com.br/api/taxas/v1"

# TX_BACEN_VEIC not supported by BrasilAPI — omit intentionally
ALIAS: dict[str, tuple[str, str]] = {
    "SELIC": ("Selic", "pct_aa"),
    "CDI": ("CDI", "pct_ad"),
    "IPCA": ("IPCA", "pct_am"),
}


class BrasilApiBacenProvider:
    name = "bacen_brasilapi"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        entry = ALIAS.get(codigo)
        if entry is None:
            return Err(f"unsupported_codigo_brasilapi: {codigo}")
        alias, unidade = entry
        try:
            data = await get_json(f"{BASE_URL}/{alias}", self._client)
            valor = Decimal(str(data["valor"]))
            if valor < 0 or valor > 100:
                return Err(f"invalid_value: {valor}")
            point = IndicatorPoint(
                codigo=codigo,
                data_referencia=date.today(),
                valor=valor,
                unidade=unidade,
                fonte="bacen_brasilapi",
            )
            return Ok([point])
        except httpx.HTTPError:
            raise
        except (KeyError, ValueError) as e:
            return Err(f"parse_error: {e}")
```

- [ ] **Step 7: Run provider tests**

```bash
cd backend && uv run pytest tests/test_bacen_providers.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/finacialsim_saas/integrations/ \
        backend/tests/test_bacen_providers.py
git commit -m "feat(phase4): add BACEN SGS + BrasilAPI providers with ProviderChain integration"
```

---

## Task 3: IndicatorsService

**Files:**
- Create: `backend/finacialsim_saas/services/indicators_service.py`
- Create: `backend/finacialsim_saas/schemas/indicators.py`
- Create: `backend/tests/test_indicators_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_indicators_service.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.integrations.bacen.schema import IndicatorPoint
from finacialsim_saas.services.indicators_service import IndicatorsService

UTC = timezone.utc


async def test_upsert_and_latest(session: AsyncSession):
    svc = IndicatorsService(session)
    point = IndicatorPoint(
        codigo="SELIC",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.75"),
        unidade="pct_aa",
        fonte="bacen_sgs",
    )
    await svc.upsert(point)
    await session.commit()

    result = await svc.latest("SELIC")
    assert result is not None
    assert result.valor == "10.75"
    assert result.codigo == "SELIC"
    assert result.stale is False  # just inserted


async def test_upsert_idempotent(session: AsyncSession):
    svc = IndicatorsService(session)
    point = IndicatorPoint(
        codigo="CDI",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.65"),
        unidade="pct_ad",
        fonte="bacen_sgs",
    )
    await svc.upsert(point)
    await session.commit()

    updated = IndicatorPoint(
        codigo="CDI",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.70"),
        unidade="pct_ad",
        fonte="bacen_sgs",
    )
    await svc.upsert(updated)
    await session.commit()

    result = await svc.latest("CDI")
    assert result is not None
    assert result.valor == "10.70"  # updated value, not duplicate row


async def test_series_returns_ordered_points(session: AsyncSession):
    svc = IndicatorsService(session)
    for i in range(1, 4):
        await svc.upsert(IndicatorPoint(
            codigo="IPCA",
            data_referencia=date(2026, i, 1),
            valor=Decimal(f"4.{i}"),
            unidade="pct_am",
            fonte="bacen_sgs",
        ))
    await session.commit()

    points = await svc.series("IPCA", "12m")
    assert len(points) == 3
    assert points[0].data_referencia <= points[-1].data_referencia


async def test_series_invalid_range_raises(session: AsyncSession):
    from finacialsim_saas.errors import AppError
    svc = IndicatorsService(session)
    with pytest.raises(AppError):
        await svc.series("SELIC", "99y")


async def test_latest_missing_returns_none(session: AsyncSession):
    svc = IndicatorsService(session)
    result = await svc.latest("NONEXISTENT")
    assert result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_indicators_service.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `schemas/indicators.py`**

```python
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class IndicatorOut(BaseModel):
    codigo: str
    valor: DecimalStr
    unidade: str
    fonte: str
    data_referencia: date
    coletado_em: datetime
    stale: bool


class SeriesPoint(BaseModel):
    data_referencia: date
    valor: DecimalStr


class SeriesOut(BaseModel):
    codigo: str
    range: str
    points: list[SeriesPoint]
```

- [ ] **Step 4: Create `services/indicators_service.py`**

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import IndicatorHistory
from finacialsim_saas.errors import AppError
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint
from finacialsim_saas.schemas.indicators import IndicatorOut, SeriesOut, SeriesPoint

UTC = timezone.utc

MAX_AGE_HOURS: dict[str, int] = {
    "SELIC": 26,
    "CDI": 26,
    "IPCA": 744,
    "TX_BACEN_VEIC": 744,
}

VALID_RANGES: dict[str, int] = {"3m": 3, "6m": 6, "12m": 12, "24m": 24}

CANONICAL_CODIGOS = ["SELIC", "CDI", "IPCA", "TX_BACEN_VEIC"]


class IndicatorsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(self, point: IndicatorPoint) -> None:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(IndicatorHistory)
            .values(
                codigo=point.codigo,
                data_referencia=point.data_referencia,
                valor=point.valor,
                unidade=point.unidade,
                fonte=point.fonte,
                payload_json=None,
                coletado_em=now,
            )
            .on_conflict_do_update(
                constraint="uq_indicators_history_codigo_date",
                set_={
                    "valor": point.valor,
                    "unidade": point.unidade,
                    "fonte": point.fonte,
                    "coletado_em": now,
                },
            )
        )
        await self._s.execute(stmt)

    async def latest(self, codigo: str) -> IndicatorOut | None:
        row = await self._s.scalar(
            select(IndicatorHistory)
            .where(IndicatorHistory.codigo == codigo)
            .order_by(IndicatorHistory.data_referencia.desc())
            .limit(1)
        )
        if row is None:
            return None
        coletado_em = row.coletado_em
        if coletado_em.tzinfo is None:
            coletado_em = coletado_em.replace(tzinfo=UTC)
        age_h = (datetime.now(UTC) - coletado_em).total_seconds() / 3600
        stale = age_h > MAX_AGE_HOURS.get(codigo, 26)
        return IndicatorOut(
            codigo=row.codigo,
            valor=row.valor,
            unidade=row.unidade,
            fonte=row.fonte,
            data_referencia=row.data_referencia,
            coletado_em=coletado_em,
            stale=stale,
        )

    async def latest_all(self) -> list[IndicatorOut]:
        results = [await self.latest(c) for c in CANONICAL_CODIGOS]
        return [r for r in results if r is not None]

    async def series(self, codigo: str, range_str: str) -> list[SeriesPoint]:
        months = VALID_RANGES.get(range_str)
        if months is None:
            raise AppError(
                f"Invalid range '{range_str}'. Valid: {list(VALID_RANGES)}",
                status_code=422,
            )
        since = date.today() - timedelta(days=months * 31)
        rows = (
            await self._s.scalars(
                select(IndicatorHistory)
                .where(
                    IndicatorHistory.codigo == codigo,
                    IndicatorHistory.data_referencia >= since,
                )
                .order_by(IndicatorHistory.data_referencia.asc())
            )
        ).all()
        return [SeriesPoint(data_referencia=r.data_referencia, valor=r.valor) for r in rows]
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_indicators_service.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/indicators_service.py \
        backend/finacialsim_saas/schemas/indicators.py \
        backend/tests/test_indicators_service.py
git commit -m "feat(phase4): IndicatorsService with upsert, latest, series + stale detection"
```

---

## Task 4: AuditService

**Files:**
- Create: `backend/finacialsim_saas/services/audit_service.py`
- Create: `backend/finacialsim_saas/schemas/audit_log.py`
- Create: `backend/tests/test_audit_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_audit_service.py`:

```python
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Role, Tenant, User
from finacialsim_saas.services.audit_service import AuditService


async def _seed_tenant_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"u-{uuid.uuid4().hex[:6]}@test.com",
        name="Test",
        password_hash="x",
        role=Role.admin,
    )
    session.add(user)
    await session.flush()
    return tenant.id, user.id


async def test_log_and_list(session: AsyncSession):
    tenant_id, user_id = await _seed_tenant_user(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    await svc.log("create", "client", uuid.uuid4(), {"before": None, "after": {"nome": "Test"}}, ctx)
    await session.commit()

    items, next_cursor = await svc.list(
        tenant_id=tenant_id,
        caller_role=Role.admin,
        caller_user_id=user_id,
    )
    assert len(items) == 1
    assert items[0].acao == "create"
    assert items[0].entidade == "client"
    assert next_cursor is None


async def test_list_user_sees_only_own(session: AsyncSession):
    tenant_id, user_id = await _seed_tenant_user(session)
    other_id = uuid.uuid4()
    ctx_self = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.user, iat=0.0)
    ctx_other = RequestContext(user_id=other_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    await svc.log("create", "simulation", uuid.uuid4(), None, ctx_self)
    await svc.log("create", "vehicle", uuid.uuid4(), None, ctx_other)
    await session.commit()

    items, _ = await svc.list(
        tenant_id=tenant_id,
        caller_role=Role.user,
        caller_user_id=user_id,
    )
    assert all(str(i.usuario_id) == str(user_id) for i in items)


async def test_cursor_pagination(session: AsyncSession):
    tenant_id, user_id = await _seed_tenant_user(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    for i in range(25):
        await svc.log("create", "vehicle", uuid.uuid4(), None, ctx)
    await session.commit()

    page1, cursor = await svc.list(tenant_id=tenant_id, caller_role=Role.admin, caller_user_id=user_id)
    assert len(page1) == 20
    assert cursor is not None

    page2, cursor2 = await svc.list(
        tenant_id=tenant_id,
        caller_role=Role.admin,
        caller_user_id=user_id,
        cursor=cursor,
    )
    assert len(page2) == 5
    assert cursor2 is None


async def test_cross_tenant_isolation(session: AsyncSession):
    tenant_a, user_a = await _seed_tenant_user(session)
    tenant_b, user_b = await _seed_tenant_user(session)
    ctx_a = RequestContext(user_id=user_a, tenant_id=tenant_a, role=Role.admin, iat=0.0)
    ctx_b = RequestContext(user_id=user_b, tenant_id=tenant_b, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    await svc.log("create", "client", uuid.uuid4(), None, ctx_a)
    await svc.log("create", "client", uuid.uuid4(), None, ctx_b)
    await session.commit()

    items_a, _ = await svc.list(tenant_id=tenant_a, caller_role=Role.admin, caller_user_id=user_a)
    assert all(str(i.tenant_id) == str(tenant_a) for i in items_a)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_audit_service.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `schemas/audit_log.py`**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    timestamp: datetime
    usuario_id: uuid.UUID | None
    acao: str
    entidade: str | None
    entidade_id: uuid.UUID | None
    diff_json: dict | None

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    next_cursor: str | None
```

- [ ] **Step 4: Create `services/audit_service.py`**

```python
from __future__ import annotations

import uuid
from base64 import b64decode, b64encode
from datetime import date, datetime, time, timezone
from typing import Any
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import AuditLog, Role

UTC = timezone.utc
PAGE_SIZE = 20


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log(
        self,
        acao: str,
        entidade: str | None,
        entidade_id: uuid.UUID | None,
        diff: dict[str, Any] | None,
        ctx: RequestContext,
    ) -> None:
        self._s.add(
            AuditLog(
                tenant_id=ctx.tenant_id,
                usuario_id=ctx.user_id,
                acao=acao,
                entidade=entidade,
                entidade_id=entidade_id,
                diff_json=diff,
            )
        )

    async def list(
        self,
        tenant_id: uuid.UUID,
        caller_role: Role,
        caller_user_id: uuid.UUID,
        usuario_id: uuid.UUID | None = None,
        entidade: str | None = None,
        acao: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
    ) -> tuple[list[AuditLog], str | None]:
        q = select(AuditLog).where(AuditLog.tenant_id == tenant_id)

        if caller_role == Role.user:
            q = q.where(AuditLog.usuario_id == caller_user_id)
        elif usuario_id is not None:
            q = q.where(AuditLog.usuario_id == usuario_id)

        if entidade:
            q = q.where(AuditLog.entidade == entidade)
        if acao:
            q = q.where(AuditLog.acao == acao)
        if date_from:
            q = q.where(AuditLog.timestamp >= datetime.combine(date_from, time.min, UTC))
        if date_to:
            q = q.where(AuditLog.timestamp <= datetime.combine(date_to, time.max, UTC))
        if cursor:
            ts, uid = _decode_cursor(cursor)
            q = q.where(
                (AuditLog.timestamp < ts)
                | ((AuditLog.timestamp == ts) & (AuditLog.id < uid))
            )

        q = q.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(PAGE_SIZE + 1)
        rows = (await self._s.scalars(q)).all()

        has_more = len(rows) > PAGE_SIZE
        items = list(rows[:PAGE_SIZE])
        next_cursor = (
            _encode_cursor(items[-1].timestamp, items[-1].id) if has_more else None
        )
        return items, next_cursor


def _encode_cursor(ts: datetime, uid: uuid.UUID) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return b64encode(json.dumps({"ts": ts.isoformat(), "id": str(uid)}).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    data = json.loads(b64decode(cursor))
    return datetime.fromisoformat(data["ts"]), uuid.UUID(data["id"])
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_audit_service.py -v
```
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/audit_service.py \
        backend/finacialsim_saas/schemas/audit_log.py \
        backend/tests/test_audit_service.py
git commit -m "feat(phase4): AuditService with log(), list(), keyset cursor, role scoping"
```

---

## Task 5: RulesService.update() with Audit + Redis

**Files:**
- Modify: `backend/finacialsim_saas/services/rules_service.py`
- Modify: `backend/finacialsim_saas/schemas/business_rules.py`
- Create: `backend/tests/test_rules_update.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_rules_update.py`:

```python
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import BusinessRule, Role, Tenant, User
from finacialsim_saas.services.rules_service import RulesService


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    t = Tenant(name="Test", slug=f"t-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    u = User(
        tenant_id=t.id, email=f"a-{uuid.uuid4().hex[:6]}@test.com",
        name="Admin", password_hash="x", role=Role.admin,
    )
    session.add(u)
    rule = BusinessRule(
        tenant_id=t.id,
        chave="entrada_minima_pct",
        valor_json={"value": "0.20"},
    )
    session.add(rule)
    await session.flush()
    return t.id, u.id


async def test_update_changes_value_and_writes_audit(session: AsyncSession):
    from finacialsim_saas.data.models import AuditLog
    from sqlalchemy import select

    tenant_id, user_id = await _seed(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    svc = RulesService(session)
    await svc.update("entrada_minima_pct", {"value": "0.30"}, ctx)
    await session.commit()

    result = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id, AuditLog.acao == "update")
    )
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].diff_json["before"] == {"value": "0.20"}
    assert logs[0].diff_json["after"] == {"value": "0.30"}
    assert logs[0].entidade == "business_rule"


async def test_update_with_motivo_stored_in_diff(session: AsyncSession):
    from finacialsim_saas.data.models import AuditLog
    from sqlalchemy import select

    tenant_id, user_id = await _seed(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    svc = RulesService(session)
    await svc.update("entrada_minima_pct", {"value": "0.25"}, ctx, motivo="Ajuste comercial")
    await session.commit()

    result = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    )
    log = result.scalar_one()
    assert log.diff_json["motivo"] == "Ajuste comercial"


async def test_update_publishes_redis_event(session: AsyncSession):
    tenant_id, user_id = await _seed(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    mock_redis = AsyncMock()
    svc = RulesService(session)
    await svc.update("entrada_minima_pct", {"value": "0.30"}, ctx, redis=mock_redis)

    mock_redis.publish.assert_awaited_once_with("rules.invalidated", str(tenant_id))


async def test_update_nonexistent_rule_raises(session: AsyncSession):
    from finacialsim_saas.errors import AppError

    t = Tenant(name="T2", slug=f"t2-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    u = User(
        tenant_id=t.id, email=f"b-{uuid.uuid4().hex[:6]}@test.com",
        name="B", password_hash="x", role=Role.admin,
    )
    session.add(u)
    await session.flush()
    ctx = RequestContext(user_id=u.id, tenant_id=t.id, role=Role.admin, iat=0.0)

    svc = RulesService(session)
    with pytest.raises(AppError):
        await svc.update("nonexistent_key", {"value": "1"}, ctx)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_rules_update.py -v
```
Expected: FAIL — `RulesService` has no `update` method.

- [ ] **Step 3: Add `BusinessRuleUpdateIn` to `schemas/business_rules.py`**

Append to the existing file:

```python
from typing import Any
from pydantic import BaseModel

class BusinessRuleUpdateIn(BaseModel):
    valor: Any
    motivo: str | None = None
```

- [ ] **Step 4: Add `update()` to `RulesService`**

Add these imports to `services/rules_service.py`:

```python
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.errors import AppError
from finacialsim_saas.services.audit_service import AuditService
```

Add the `update` method to `RulesService`:

```python
    async def update(
        self,
        chave: str,
        valor: Any,
        ctx: RequestContext,
        motivo: str | None = None,
        redis: Any | None = None,
    ) -> None:
        result = await self._s.execute(
            select(BusinessRule).where(
                BusinessRule.tenant_id == ctx.tenant_id,
                BusinessRule.chave == chave,
            )
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise AppError(f"business rule not found: {chave}", status_code=404)

        before = rule.valor_json
        rule.valor_json = valor
        rule.atualizado_em = datetime.now(timezone.utc)
        rule.atualizado_por = ctx.user_id

        diff: dict[str, Any] = {"before": before, "after": valor}
        if motivo:
            diff["motivo"] = motivo

        audit = AuditService(self._s)
        await audit.log("update", "business_rule", rule.id, diff, ctx)

        if redis is not None:
            await redis.publish("rules.invalidated", str(ctx.tenant_id))
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_rules_update.py -v
```
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/rules_service.py \
        backend/finacialsim_saas/schemas/business_rules.py \
        backend/tests/test_rules_update.py
git commit -m "feat(phase4): RulesService.update() with audit log + Redis pub/sub"
```

---

## Task 6: Lifespan Redis + ARQ Worker Setup

**Files:**
- Modify: `backend/finacialsim_saas/main.py`
- Modify: `backend/finacialsim_saas/workers/tasks.py`
- Modify: `backend/finacialsim_saas/workers/worker.py`
- Create: `backend/tests/test_arq_jobs.py`

- [ ] **Step 1: Add Redis client to lifespan in `main.py`**

Add import at the top of `main.py`:

```python
import redis.asyncio as aioredis
```

Modify the `lifespan` function — add Redis setup after `app.state.fipe_chain`:

```python
    app.state.redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
    await app.state.redis.aclose()
    await engine.dispose()
    logger.info("shutdown")
```

(Move the existing `yield` and `engine.dispose` to after the Redis close.)

- [ ] **Step 2: Replace `workers/tasks.py` with job functions**

```python
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import delete, select

from finacialsim_saas.data.models import FipeCache, IndicatorHistory, ProviderHealth
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint
from finacialsim_saas.services.indicators_service import IndicatorsService

UTC = timezone.utc

BACEN_CODIGOS = ["SELIC", "CDI", "IPCA", "TX_BACEN_VEIC"]
PROVIDER_PING_URLS = {
    "fipe_parallelum": "https://parallelum.com.br/fipe/api/v1/carros/marcas",
    "fipe_brasilapi": "https://brasilapi.com.br/api/fipe/marcas/v1/carros",
    "bacen_sgs": (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
    ),
    "bacen_brasilapi": "https://brasilapi.com.br/api/taxas/v1/Selic",
}


async def ping(ctx: dict) -> str:
    """Health-check job. Enqueue it to verify the worker is alive and Redis is reachable."""
    logger.info("ping job executed")
    return "pong"


async def update_bacen_indicators(ctx: dict) -> None:
    today = date.today()
    lock_key = f"lock:update_bacen_indicators:{today.isoformat()}"
    redis = ctx["redis"]
    acquired = await redis.set(lock_key, "1", nx=True, ex=86400)
    if not acquired:
        logger.info("update_bacen_indicators: already ran today, skipping")
        return

    chain = ctx["bacen_chain"]
    session_factory = ctx["session_factory"]
    one_year_ago = date(today.year - 1, today.month, today.day)

    async with session_factory() as session:
        svc = IndicatorsService(session)
        for codigo in BACEN_CODIGOS:
            result = await chain.fetch({
                "codigo": codigo,
                "data_inicial": one_year_ago,
                "data_final": today,
            })
            if result.is_ok:
                for point in result.value:
                    await svc.upsert(point)
                await session.commit()
                logger.info(f"update_bacen_indicators: {codigo} ok ({len(result.value)} pts)")
            else:
                logger.warning(f"update_bacen_indicators: {codigo} failed: {result.error}")


async def prune_fipe_cache(ctx: dict) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        now = datetime.now(UTC)
        # Delete rows where coletado_em + ttl_horas * interval has passed
        from sqlalchemy import text
        await session.execute(
            text(
                "DELETE FROM fipe_cache "
                "WHERE coletado_em + ttl_horas * interval '1 hour' < :now"
            ),
            {"now": now},
        )
        await session.commit()
    logger.info("prune_fipe_cache: complete")


async def verify_provider_health(ctx: dict) -> None:
    http: httpx.AsyncClient = ctx["http_client"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        for provider_name, url in PROVIDER_PING_URLS.items():
            start = time.monotonic()
            try:
                resp = await http.get(url, timeout=10.0)
                latency_ms = int((time.monotonic() - start) * 1000)
                success = resp.status_code < 400
                error = None if success else f"HTTP {resp.status_code}"
            except Exception as exc:
                latency_ms = None
                success = False
                error = str(exc)[:200]

            session.add(
                ProviderHealth(
                    provider_name=provider_name,
                    latency_ms=latency_ms,
                    success=success,
                    error=error,
                )
            )
            await session.flush()

            keep_ids = (
                await session.scalars(
                    select(ProviderHealth.id)
                    .where(ProviderHealth.provider_name == provider_name)
                    .order_by(ProviderHealth.checked_at.desc())
                    .limit(50)
                )
            ).all()
            await session.execute(
                delete(ProviderHealth).where(
                    ProviderHealth.provider_name == provider_name,
                    ~ProviderHealth.id.in_(keep_ids),
                )
            )

        await session.commit()
    logger.info("verify_provider_health: complete")
```

- [ ] **Step 3: Update `workers/worker.py` with cron jobs + on_startup/shutdown**

```python
import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.integrations.bacen.brasilapi import BrasilApiBacenProvider
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.settings import get_settings
from finacialsim_saas.workers.tasks import (
    ping,
    prune_fipe_cache,
    update_bacen_indicators,
    verify_provider_health,
)
from finacialsim_core.integrations.base import ProviderChain


def get_redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings.from_dsn(str(s.redis_url))


async def startup(ctx: dict) -> None:
    settings = get_settings()
    engine = build_engine(str(settings.database_url))
    ctx["engine"] = engine
    ctx["session_factory"] = build_session_factory(engine)
    ctx["http_client"] = httpx.AsyncClient(timeout=10.0)
    ctx["bacen_chain"] = ProviderChain([
        BcbSgsProvider(ctx["http_client"]),
        BrasilApiBacenProvider(ctx["http_client"]),
    ])


async def shutdown(ctx: dict) -> None:
    await ctx["http_client"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [ping]
    cron_jobs = [
        cron(update_bacen_indicators, hour=12, minute=0),   # 09:00 BRT = 12:00 UTC
        cron(prune_fipe_cache, hour=6, minute=0),            # 03:00 BRT = 06:00 UTC
        cron(verify_provider_health, hour={0, 6, 12, 18}, minute=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 60
```

- [ ] **Step 4: Write ARQ job tests**

Create `backend/tests/test_arq_jobs.py`:

```python
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_core.integrations.base import ProviderChain
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import IndicatorHistory, ProviderHealth
from finacialsim_saas.integrations.bacen.sgs import BcbSgsProvider
from finacialsim_saas.workers.tasks import (
    update_bacen_indicators,
    verify_provider_health,
    prune_fipe_cache,
)


def _make_sgs_response(valor: str = "10.75") -> list[dict]:
    return [{"data": "01/06/2026", "valor": valor}]


@respx.mock
async def test_update_bacen_indicators_populates_db(engine: AsyncEngine, redis_url: str):
    from arq.connections import RedisSettings, create_pool

    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("10.75"))
    )
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("10.65"))
    )
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("4.50"))
    )
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.20714/dados").mock(
        return_value=httpx.Response(200, json=_make_sgs_response("1.85"))
    )

    session_factory = build_session_factory(engine)
    redis_pool = await create_pool(RedisSettings.from_dsn(redis_url))
    http_client = httpx.AsyncClient()
    ctx = {
        "redis": redis_pool,
        "session_factory": session_factory,
        "http_client": http_client,
        "bacen_chain": ProviderChain([BcbSgsProvider(http_client)]),
    }

    await update_bacen_indicators(ctx)

    async with session_factory() as s:
        count = await s.scalar(select(func.count(IndicatorHistory.id)))
    assert count == 4

    # Second call blocked by lock
    await update_bacen_indicators(ctx)

    async with session_factory() as s:
        count2 = await s.scalar(select(func.count(IndicatorHistory.id)))
    assert count2 == 4  # idempotent

    await redis_pool.aclose()
    await http_client.aclose()


@respx.mock
async def test_verify_provider_health_prunes_to_50(engine: AsyncEngine):
    session_factory = build_session_factory(engine)

    for provider in ["fipe_parallelum", "fipe_brasilapi", "bacen_sgs", "bacen_brasilapi"]:
        respx.get(
            url__regex=r"https://(parallelum\.com\.br|brasilapi\.com\.br|api\.bcb\.gov\.br).*"
        ).mock(return_value=httpx.Response(200, json=[]))

    http_client = httpx.AsyncClient()
    ctx = {"http_client": http_client, "session_factory": session_factory}

    # Run 55 times to verify pruning to 50
    for _ in range(55):
        await verify_provider_health(ctx)

    async with session_factory() as s:
        count = await s.scalar(
            select(func.count(ProviderHealth.id)).where(
                ProviderHealth.provider_name == "fipe_parallelum"
            )
        )
    assert count == 50

    await http_client.aclose()
```

- [ ] **Step 5: Run job tests**

```bash
cd backend && uv run pytest tests/test_arq_jobs.py -v
```
Expected: Both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/main.py \
        backend/finacialsim_saas/workers/tasks.py \
        backend/finacialsim_saas/workers/worker.py \
        backend/tests/test_arq_jobs.py
git commit -m "feat(phase4): ARQ cron jobs for BACEN update, FIPE prune, provider health check"
```

---

## Task 7: Indicators API

**Files:**
- Create: `backend/finacialsim_saas/api/indicators.py`
- Modify: `backend/finacialsim_saas/main.py`
- Create: `backend/tests/test_indicators_endpoints.py`

- [ ] **Step 1: Write failing endpoint tests**

Create `backend/tests/test_indicators_endpoints.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import IndicatorHistory, Role, Tenant, User
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import get_settings


async def _seed_staff(engine: AsyncEngine) -> tuple[str, str]:
    """Returns (tenant_id_str, access_token)."""
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name="ITest", slug=f"itest-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"staff-{uuid.uuid4().hex[:6]}@test.com",
            password="pw",
            name="Staff",
            role=Role.admin,
        )
        tokens = await svc.issue_tokens(user)
        await session.commit()
        return str(t.id), tokens["access_token"]


async def _seed_indicator(engine: AsyncEngine, codigo: str = "SELIC") -> None:
    from finacialsim_saas.services.indicators_service import IndicatorsService
    from finacialsim_saas.integrations.bacen.schema import IndicatorPoint

    factory = build_session_factory(engine)
    async with factory() as s:
        svc = IndicatorsService(s)
        await svc.upsert(IndicatorPoint(
            codigo=codigo,
            data_referencia=date(2026, 6, 1),
            valor=Decimal("10.75"),
            unidade="pct_aa",
            fonte="bacen_sgs",
        ))
        await s.commit()


async def test_list_indicators_returns_array(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_staff(engine)
    await _seed_indicator(engine, "SELIC")
    await _seed_indicator(engine, "CDI")

    resp = await client.get(
        "/api/v1/indicators", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    codigos = [d["codigo"] for d in data]
    assert "SELIC" in codigos


async def test_indicator_series(client: AsyncClient, engine: AsyncEngine):
    _, token = await _seed_staff(engine)
    await _seed_indicator(engine, "IPCA")

    resp = await client.get(
        "/api/v1/indicators/IPCA/series?range=12m",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["codigo"] == "IPCA"
    assert isinstance(data["points"], list)


async def test_refresh_indicators_requires_admin(client: AsyncClient, engine: AsyncEngine):
    from finacialsim_saas.data.database import build_session_factory
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name="R2", slug=f"r2-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"usr-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U", role=Role.user,
        )
        tokens = await svc.issue_tokens(user)
        await s.commit()
        token = tokens["access_token"]

    resp = await client.post(
        "/api/v1/indicators/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_indicators_endpoints.py -v
```
Expected: 404 — routes not registered.

- [ ] **Step 3: Create `api/indicators.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.schemas.indicators import IndicatorOut, SeriesOut
from finacialsim_saas.services.indicators_service import IndicatorsService

router = APIRouter(prefix="/api/v1", tags=["indicators"])


@router.get("/indicators", response_model=list[IndicatorOut])
async def list_indicators(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[IndicatorOut]:
    return await IndicatorsService(session).latest_all()


@router.get("/indicators/{codigo}/series", response_model=SeriesOut)
async def get_indicator_series(
    codigo: str,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    range: str = Query(default="12m"),
) -> SeriesOut:
    svc = IndicatorsService(session)
    points = await svc.series(codigo, range)
    return SeriesOut(codigo=codigo, range=range, points=points)


@router.post("/indicators/refresh", status_code=202)
async def refresh_indicators(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    request: Request,
) -> dict[str, bool]:
    from arq.connections import ArqRedis
    redis: ArqRedis = request.app.state.redis
    await redis.enqueue_job("update_bacen_indicators")
    return {"enqueued": True}
```

- [ ] **Step 4: Register router in `main.py`**

Add after existing router imports:

```python
from finacialsim_saas.api.indicators import router as indicators_router  # noqa: E402
```

Add after `app.include_router(cep_router)`:

```python
app.include_router(indicators_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_indicators_endpoints.py -v
```
Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/api/indicators.py \
        backend/finacialsim_saas/main.py \
        backend/tests/test_indicators_endpoints.py
git commit -m "feat(phase4): indicators API — list, series, refresh endpoints"
```

---

## Task 8: Business Rules PUT API

**Files:**
- Modify: `backend/finacialsim_saas/api/business_rules.py`
- Modify: `backend/finacialsim_saas/main.py` (conftest needs redis on app.state)

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_simulation_endpoints.py` (or create a new file `test_business_rules_update.py`):

Create `backend/tests/test_business_rules_update.py`:

```python
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import BusinessRule, Role, Tenant, User
from finacialsim_saas.settings import get_settings


async def _seed_admin(engine: AsyncEngine) -> tuple[uuid.UUID, str]:
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name="RuleTest", slug=f"rt-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        rule = BusinessRule(
            tenant_id=t.id,
            chave="entrada_minima_pct",
            valor_json="0.20",  # stored as raw JSON string, not wrapped in dict
        )
        session.add(rule)
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"adm-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Admin", role=Role.admin,
        )
        tokens = await svc.issue_tokens(user)
        await session.commit()
        return t.id, tokens["access_token"]


async def test_put_business_rule_updates_value(client: AsyncClient, engine: AsyncEngine):
    tenant_id, token = await _seed_admin(engine)

    resp = await client.put(
        "/api/v1/business-rules/entrada_minima_pct",
        json={"valor": "0.30"},  # raw string — stored as-is in valor_json
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Verify via GET
    resp2 = await client.get(
        "/api/v1/business-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp2.json()
    assert data["entrada_minima_pct"] == "0.30"


async def test_put_business_rule_non_admin_forbidden(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name="T3", slug=f"t3-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        u = await svc.register_user(
            tenant_id=t.id,
            email=f"mgr-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="Mgr", role=Role.manager,
        )
        tokens = await svc.issue_tokens(u)
        await s.commit()
        token = tokens["access_token"]

    resp = await client.put(
        "/api/v1/business-rules/entrada_minima_pct",
        json={"valor": "0.40"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_business_rules_update.py -v
```
Expected: FAIL — no PUT endpoint.

- [ ] **Step 3: Patch conftest to inject mock Redis on app.state**

The PUT handler calls `request.app.state.redis.publish(...)`. The test `client` fixture doesn't go through lifespan, so `app.state.redis` won't exist. Add a mock to the existing `client` fixture in `conftest.py`:

```python
from unittest.mock import AsyncMock

@pytest_asyncio.fixture
async def client(engine: AsyncEngine):
    from httpx import ASGITransport, AsyncClient
    from finacialsim_saas.main import app, app_state
    from finacialsim_saas.data.database import build_session_factory

    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.redis = AsyncMock()  # Add this line
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [ ] **Step 4: Add PUT endpoint to `api/business_rules.py`**

```python
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.schemas.business_rules import BusinessRulesOut, BusinessRuleUpdateIn, RateCurvePointOut
from finacialsim_saas.services.rules_service import RulesService

router = APIRouter(prefix="/api/v1", tags=["business-rules"])


@router.get("/business-rules", response_model=BusinessRulesOut)
async def get_business_rules(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessRulesOut:
    svc = RulesService(session)
    rules = await svc.get_rules(ctx.tenant_id)
    curva_raw = rules.get("taxa_por_prazo_curva", [])
    return BusinessRulesOut(
        entrada_minima_pct=rules["entrada_minima_pct"],
        prazo_minimo_meses=int(rules["prazo_minimo_meses"]),
        prazo_maximo_meses=int(rules["prazo_maximo_meses"]),
        taxa_minima_mes=rules["taxa_minima_mes"],
        taxa_maxima_mes=rules["taxa_maxima_mes"],
        dias_max_carencia=int(rules["dias_max_carencia"]),
        valor_minimo_financiado=rules["valor_minimo_financiado"],
        iof_fixo_pct=rules["iof_fixo_pct"],
        iof_diario_pct=rules["iof_diario_pct"],
        iof_diario_max_dias=int(rules["iof_diario_max_dias"]),
        incluir_iof_default=bool(rules["incluir_iof_default"]),
        rateio_ipva_meses_default=int(rules["rateio_ipva_meses_default"]),
        rateio_emplacamento_meses_default=int(rules["rateio_emplacamento_meses_default"]),
        taxa_por_prazo_curva=[
            RateCurvePointOut(ate_meses=p["ate_meses"], taxa_mensal=p["taxa_mensal"])
            for p in curva_raw
        ],
    )


@router.put("/business-rules/{chave}", status_code=204)
async def update_business_rule(
    chave: str,
    body: BusinessRuleUpdateIn,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    svc = RulesService(session)
    await svc.update(chave, body.valor, ctx, motivo=body.motivo, redis=redis)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_business_rules_update.py -v
```
Expected: Both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/api/business_rules.py \
        backend/finacialsim_saas/schemas/business_rules.py \
        backend/tests/conftest.py \
        backend/tests/test_business_rules_update.py
git commit -m "feat(phase4): PUT /business-rules/{chave} endpoint (admin-only) with audit + Redis"
```

---

## Task 9: Audit Log API

**Files:**
- Create: `backend/finacialsim_saas/api/audit_log.py`
- Modify: `backend/finacialsim_saas/main.py`
- Create: `backend/tests/test_audit_log_endpoints.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_audit_log_endpoints.py`:

```python
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant, User
from finacialsim_saas.services.audit_service import AuditService
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.settings import get_settings


async def _seed(engine: AsyncEngine, role: Role = Role.admin) -> tuple[uuid.UUID, str, uuid.UUID]:
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name=f"AL-{role.value}", slug=f"al-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        u = await svc.register_user(
            tenant_id=t.id,
            email=f"al-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U", role=role,
        )
        tokens = await svc.issue_tokens(u)

        # Write some audit entries
        audit = AuditService(s)
        ctx = RequestContext(user_id=u.id, tenant_id=t.id, role=role, iat=0.0)
        for i in range(3):
            await audit.log("create", "client", uuid.uuid4(), None, ctx)
        await s.commit()
        return t.id, tokens["access_token"], u.id


async def test_audit_log_returns_entries(client: AsyncClient, engine: AsyncEngine):
    _, token, _ = await _seed(engine)
    resp = await client.get(
        "/api/v1/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 3
    assert data["next_cursor"] is None


async def test_audit_log_filter_by_acao(client: AsyncClient, engine: AsyncEngine):
    _, token, _ = await _seed(engine)
    resp = await client.get(
        "/api/v1/audit-log?acao=create",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["acao"] == "create" for i in items)


async def test_audit_log_user_role_sees_only_own(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name="UserScope", slug=f"us-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        u1 = await svc.register_user(
            tenant_id=t.id,
            email=f"u1-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U1", role=Role.user,
        )
        u2 = await svc.register_user(
            tenant_id=t.id,
            email=f"u2-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U2", role=Role.admin,
        )
        tokens1 = await svc.issue_tokens(u1)
        audit = AuditService(s)
        ctx1 = RequestContext(user_id=u1.id, tenant_id=t.id, role=Role.user, iat=0.0)
        ctx2 = RequestContext(user_id=u2.id, tenant_id=t.id, role=Role.admin, iat=0.0)
        await audit.log("create", "simulation", uuid.uuid4(), None, ctx1)
        await audit.log("create", "vehicle", uuid.uuid4(), None, ctx2)
        await s.commit()
        token1 = tokens1["access_token"]

    resp = await client.get(
        "/api/v1/audit-log",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["usuario_id"] == str(u1.id) for i in items)


async def test_audit_log_csv_export(client: AsyncClient, engine: AsyncEngine):
    _, token, _ = await _seed(engine)
    resp = await client.get(
        "/api/v1/audit-log?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert b"acao" in resp.content


async def test_audit_log_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/audit-log")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_audit_log_endpoints.py -v
```
Expected: FAIL — route not registered.

- [ ] **Step 3: Create `api/audit_log.py`**

```python
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.audit_log import AuditLogItem, AuditLogPage
from finacialsim_saas.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1", tags=["audit-log"])


@router.get("/audit-log")
async def list_audit_log(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    usuario_id: uuid.UUID | None = None,
    entidade: str | None = None,
    acao: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    format: str | None = None,
) -> AuditLogPage | StreamingResponse:
    svc = AuditService(session)
    items, next_cursor = await svc.list(
        tenant_id=ctx.tenant_id,
        caller_role=ctx.role,
        caller_user_id=ctx.user_id,
        usuario_id=usuario_id,
        entidade=entidade,
        acao=acao,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
    )

    if format == "csv":
        return _build_csv_response(items)

    return AuditLogPage(
        items=[AuditLogItem.model_validate(i) for i in items],
        next_cursor=next_cursor,
    )


def _build_csv_response(items: list) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "acao", "entidade", "entidade_id", "usuario_id", "diff_json"])
    for row in items:
        writer.writerow([
            row.timestamp.isoformat(),
            row.acao,
            row.entidade or "",
            str(row.entidade_id) if row.entidade_id else "",
            str(row.usuario_id) if row.usuario_id else "",
            json.dumps(row.diff_json) if row.diff_json else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )
```

- [ ] **Step 4: Register router in `main.py`**

```python
from finacialsim_saas.api.audit_log import router as audit_log_router  # noqa: E402
```

```python
app.include_router(audit_log_router)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_audit_log_endpoints.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/api/audit_log.py \
        backend/finacialsim_saas/main.py \
        backend/tests/test_audit_log_endpoints.py
git commit -m "feat(phase4): GET /audit-log endpoint with filters, cursor pagination, CSV export"
```

---

## Task 10: Audit Backfill — AuthService

**Files:**
- Modify: `backend/finacialsim_saas/auth/service.py`
- Create: `backend/tests/test_audit_backfill.py` (partial — add first section)

The `AuthService` needs to write audit entries for `register_user`. But `AuthService.__init__` takes `session` and `settings` — we can instantiate `AuditService(self._s)` internally.

The challenge: `AuthService.register_user` doesn't have a `ctx: RequestContext`. The action comes from an admin. The API handler (`users.py` or `cli/main.py`) has the ctx. We need to add `ctx` parameter.

Check: `backend/finacialsim_saas/api/users.py` calls `register_user`. Read it first to confirm the call signature.

- [ ] **Step 1: Read `api/users.py` to understand current call site**

```bash
cd backend && grep -n "register_user" finacialsim_saas/api/users.py finacialsim_saas/cli/main.py
```
Expected output shows line numbers where `register_user` is called.

- [ ] **Step 2: Write failing test (add to new file)**

Create `backend/tests/test_audit_backfill.py`:

```python
"""Integration tests: every CUD operation produces a correct audit_log entry."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import AuditLog, Role, Tenant, User
from finacialsim_saas.settings import get_settings


async def _make_tenant_admin(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, str]:
    t = Tenant(name=f"BF-{uuid.uuid4().hex[:6]}", slug=f"bf-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, get_settings())
    user = await svc.register_user(
        tenant_id=t.id,
        email=f"adm-{uuid.uuid4().hex[:6]}@test.com",
        password="pw", name="Admin", role=Role.admin,
    )
    await session.flush()
    return t.id, user.id, str(user.email)


async def test_register_user_creates_audit_entry(session: AsyncSession):
    from finacialsim_saas.auth.service import AuthService
    from sqlalchemy import select

    t = Tenant(name=f"Au-{uuid.uuid4().hex[:6]}", slug=f"au-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()

    creator_id = uuid.uuid4()
    ctx = RequestContext(user_id=creator_id, tenant_id=t.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())
    new_user = await svc.register_user(
        tenant_id=t.id,
        email=f"new-{uuid.uuid4().hex[:6]}@test.com",
        password="pw", name="New", role=Role.user,
        ctx=ctx,
    )
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog).where(AuditLog.tenant_id == t.id, AuditLog.acao == "create")
    )).all()
    assert len(logs) == 1
    assert logs[0].entidade == "user"
    assert logs[0].diff_json["after"]["email"] == new_user.email
```

- [ ] **Step 3: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_register_user_creates_audit_entry -v
```
Expected: FAIL — `register_user` missing `ctx` parameter.

- [ ] **Step 4: Add `ctx` param and audit call to `AuthService.register_user`**

In `auth/service.py`, import `AuditService`:

```python
from finacialsim_saas.services.audit_service import AuditService
```

Change the `register_user` signature to accept an optional `ctx`:

```python
    async def register_user(
        self, *, tenant_id: uuid.UUID, email: str, password: str,
        name: str, role: Role,
        ctx: "RequestContext | None" = None,
    ) -> User:
```

At the end of `register_user`, after `self._s.add(user)` and `await self._s.flush()`:

```python
        if ctx is not None:
            audit = AuditService(self._s)
            await audit.log(
                "create", "user", user.id,
                {"before": None, "after": {"email": email, "name": name, "role": role.value}},
                ctx,
            )
```

- [ ] **Step 5: Update callers**

All existing `register_user` callers that don't pass `ctx` still work because `ctx=None` is the default (no audit when called from CLI or setup fixtures).

Update the admin user creation endpoint in `api/users.py` to pass `ctx`:

```python
# In the create_user endpoint, add ctx to the register_user call:
await svc.register_user(..., ctx=ctx)
```

Find the exact location with:
```bash
grep -n "register_user" backend/finacialsim_saas/api/users.py
```

- [ ] **Step 6: Run test**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_register_user_creates_audit_entry -v
```
Expected: PASS.

- [ ] **Step 7: Run full test suite to verify no regressions**

```bash
cd backend && uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: All tests PASS (existing tests pass `ctx=None` implicitly).

- [ ] **Step 8: Commit**

```bash
git add backend/finacialsim_saas/auth/service.py \
        backend/finacialsim_saas/api/users.py \
        backend/tests/test_audit_backfill.py
git commit -m "feat(phase4): audit log on AuthService.register_user"
```

---

## Task 11: Audit Backfill — ClientService

**Files:**
- Modify: `backend/finacialsim_saas/services/client_service.py`
- Modify: `backend/tests/test_audit_backfill.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_audit_backfill.py`:

```python
async def test_client_create_update_deactivate_audit(session: AsyncSession):
    from finacialsim_saas.services.client_service import ClientService
    from finacialsim_saas.schemas.clients import ClientIn

    tenant_id, user_id, _ = await _make_tenant_admin(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = ClientService(session)

    client = await svc.create(
        ClientIn(
            nome="João Silva",
            cpf_cnpj="529.982.247-25",
            tipo="pf",
        ),
        ctx,
    )
    await session.flush()

    await svc.update(client.id, ClientIn(nome="João S. Updated", cpf_cnpj="529.982.247-25", tipo="pf"), ctx)
    await session.flush()

    await svc.deactivate(client.id, ctx)
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.entidade == "client")
        .order_by(AuditLog.timestamp.asc())
    )).all()

    assert len(logs) == 3
    assert logs[0].acao == "create"
    assert logs[0].diff_json["before"] is None
    assert logs[1].acao == "update"
    assert logs[1].diff_json["before"] is not None
    assert logs[2].acao == "deactivate"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_client_create_update_deactivate_audit -v
```
Expected: FAIL — no audit entries.

- [ ] **Step 3: Add audit calls to `client_service.py`**

Add import:

```python
from finacialsim_saas.services.audit_service import AuditService
```

In `ClientService.create`, after `await self._s.flush()` (after client has an ID):

```python
        audit = AuditService(self._s)
        await audit.log(
            "create", "client", client.id,
            {"before": None, "after": _serialize_client(client)},
            ctx,
        )
```

In `ClientService.update`, capture before-state first, then after modification:

```python
        before = _serialize_client(existing_client)
        # ... existing update code ...
        await self._s.flush()
        audit = AuditService(self._s)
        await audit.log(
            "update", "client", existing_client.id,
            {"before": before, "after": _serialize_client(existing_client)},
            ctx,
        )
```

In `ClientService.deactivate`:

```python
        audit = AuditService(self._s)
        await audit.log(
            "deactivate", "client", client.id,
            {"before": {"is_active": True}, "after": {"is_active": False}},
            ctx,
        )
```

Add serializer helper at module level (not a method):

```python
def _serialize_client(c: "Client") -> dict:
    return {
        "id": str(c.id),
        "nome": c.nome,
        "cpf_cnpj": c.cpf_cnpj,
        "tipo": c.tipo.value,
        "is_active": c.is_active,
        "email": c.email,
        "telefone": c.telefone,
    }
```

- [ ] **Step 4: Run test**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_client_create_update_deactivate_audit -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
cd backend && uv run pytest tests/ -x --tb=short 2>&1 | tail -20
```
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/client_service.py \
        backend/tests/test_audit_backfill.py
git commit -m "feat(phase4): audit log on ClientService create/update/deactivate"
```

---

## Task 12: Audit Backfill — VehicleService

**Files:**
- Modify: `backend/finacialsim_saas/services/vehicle_service.py`
- Modify: `backend/tests/test_audit_backfill.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_audit_backfill.py`:

```python
async def test_vehicle_create_update_status_audit(session: AsyncSession):
    from finacialsim_saas.services.vehicle_service import VehicleService
    from finacialsim_saas.schemas.vehicles import VehicleIn

    tenant_id, user_id, _ = await _make_tenant_admin(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = VehicleService(session)

    vehicle = await svc.create(
        VehicleIn(
            fonte="manual",
            tipo="carro",
            marca="Toyota",
            modelo="Corolla",
            ano_modelo=2023,
            valor_referencia="120000.00",
        ),
        ctx,
    )
    await session.flush()

    await svc.set_status(vehicle.id, "reservado", ctx)
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.entidade == "vehicle")
        .order_by(AuditLog.timestamp.asc())
    )).all()

    assert len(logs) == 2
    assert logs[0].acao == "create"
    assert logs[1].acao == "set_status"
    assert logs[1].diff_json["after"]["status"] == "reservado"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_vehicle_create_update_status_audit -v
```
Expected: FAIL.

- [ ] **Step 3: Add audit calls to `vehicle_service.py`**

Add import:

```python
from finacialsim_saas.services.audit_service import AuditService
```

Add module-level serializer:

```python
def _serialize_vehicle(v: "Vehicle") -> dict:
    return {
        "id": str(v.id),
        "marca": v.marca,
        "modelo": v.modelo,
        "ano_modelo": v.ano_modelo,
        "status": v.status.value,
        "fonte": v.fonte,
    }
```

In `VehicleService.create`, after flush:

```python
        audit = AuditService(self._s)
        await audit.log(
            "create", "vehicle", vehicle.id,
            {"before": None, "after": _serialize_vehicle(vehicle)},
            ctx,
        )
```

In `VehicleService.set_status`, before updating, capture before:

```python
        before_status = vehicle.status.value
        # ... existing status update ...
        audit = AuditService(self._s)
        await audit.log(
            "set_status", "vehicle", vehicle.id,
            {"before": {"status": before_status}, "after": {"status": new_status}},
            ctx,
        )
```

In `VehicleService.update` (if it exists — add similar pattern):

```python
        before = _serialize_vehicle(vehicle)
        # ... update fields ...
        audit = AuditService(self._s)
        await audit.log(
            "update", "vehicle", vehicle.id,
            {"before": before, "after": _serialize_vehicle(vehicle)},
            ctx,
        )
```

- [ ] **Step 4: Run test + full suite**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_vehicle_create_update_status_audit tests/ -x --tb=short 2>&1 | tail -20
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/vehicle_service.py \
        backend/tests/test_audit_backfill.py
git commit -m "feat(phase4): audit log on VehicleService create/update/set_status"
```

---

## Task 13: Audit Backfill — SimulationService

**Files:**
- Modify: `backend/finacialsim_saas/services/simulation_service.py`
- Modify: `backend/tests/test_audit_backfill.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_audit_backfill.py`:

```python
async def test_simulation_create_status_change_audit(session: AsyncSession):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.services.rules_service import RulesService

    tenant_id, user_id, _ = await _make_tenant_admin(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    # Seed required business rules
    from finacialsim_saas.data.models import BusinessRule
    from decimal import Decimal
    # valor_json stores raw JSON values (not wrapped in dicts) — check existing
    # test_simulation_service.py rules_seeded fixture for the canonical format.
    rules_data = {
        "entrada_minima_pct": "0.20",
        "prazo_minimo_meses": 12,
        "prazo_maximo_meses": 60,
        "taxa_minima_mes": "0.005",
        "taxa_maxima_mes": "0.03",
        "dias_max_carencia": 90,
        "valor_minimo_financiado": "5000.00",
        "iof_fixo_pct": "0.0038",
        "iof_diario_pct": "0.000082",
        "iof_diario_max_dias": 365,
        "incluir_iof_default": True,
        "rateio_ipva_meses_default": 12,
        "rateio_emplacamento_meses_default": 3,
        "taxa_por_prazo_curva": [],
    }
    for chave, valor_json in rules_data.items():
        session.add(BusinessRule(tenant_id=tenant_id, chave=chave, valor_json=valor_json))
    await session.flush()

    svc = SimulationService(session)
    from finacialsim_saas.schemas.simulations import SimulationCreate
    from datetime import date

    sim = await svc.create(
        SimulationCreate(
            valor_veiculo="100000.00",
            valor_entrada="20000.00",
            taxa_mensal="0.012",
            prazo_meses=36,
            data_liberacao=date(2026, 6, 1).isoformat(),
            primeiro_vencimento=date(2026, 7, 1).isoformat(),
            incluir_iof=True,
            fees=[],
            extras=[],
        ),
        ctx,
    )
    await session.flush()

    # Archive the simulation
    await svc.archive(sim.id, ctx)
    await session.commit()

    logs = (await session.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.entidade == "simulation")
        .order_by(AuditLog.timestamp.asc())
    )).all()

    assert len(logs) == 2
    assert logs[0].acao == "create"
    assert logs[1].acao == "archive"
    assert logs[1].diff_json["after"]["status"] == "arquivado"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py::test_simulation_create_status_change_audit -v
```
Expected: FAIL.

Note: If `SimulationService` has no `archive` method, check the actual method name by running:

```bash
grep -n "def " backend/finacialsim_saas/services/simulation_service.py
```

Adjust the test to use the correct method name.

- [ ] **Step 3: Add audit calls to `simulation_service.py`**

Add import:

```python
from finacialsim_saas.services.audit_service import AuditService
```

In `SimulationService.create`, after the simulation is flushed and has an ID:

```python
        audit = AuditService(self._s)
        await audit.log(
            "create", "simulation", sim.id,
            {"before": None, "after": {"id": str(sim.id), "codigo": sim.codigo, "status": sim.status.value}},
            ctx,
        )
```

In any status-change method (archive, confirm, etc.), capture before and after:

```python
        before_status = sim.status.value
        sim.status = SimulationStatus.arquivado
        audit = AuditService(self._s)
        await audit.log(
            "archive", "simulation", sim.id,
            {"before": {"status": before_status}, "after": {"status": "arquivado"}},
            ctx,
        )
```

- [ ] **Step 4: Run test + full suite**

```bash
cd backend && uv run pytest tests/test_audit_backfill.py tests/ -x --tb=short 2>&1 | tail -25
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/simulation_service.py \
        backend/tests/test_audit_backfill.py
git commit -m "feat(phase4): audit log on SimulationService create + status changes"
```

---

## Task 14: Final Verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && uv run pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: All tests PASS. No failures, no errors.

- [ ] **Step 2: Run linter + type-check**

```bash
cd backend && uv run ruff check . && uv run mypy finacialsim_saas/
```
Expected: No issues. Fix any mypy complaints before proceeding.

- [ ] **Step 3: Verify migration chain**

```bash
cd backend && uv run alembic history
```
Confirm `005` appears in the chain after `004`.

- [ ] **Step 4: Acceptance check — list**

- [ ] `POST /api/v1/indicators/refresh` returns 202 with admin token
- [ ] `GET /api/v1/indicators` returns array with `stale` field
- [ ] `GET /api/v1/indicators/SELIC/series?range=12m` returns `{codigo, range, points}`
- [ ] `PUT /api/v1/business-rules/entrada_minima_pct` returns 204; next GET reflects new value
- [ ] `GET /api/v1/audit-log` returns paginated items; user role sees only own
- [ ] `GET /api/v1/audit-log?format=csv` returns CSV with `acao` column
- [ ] Each CUD on client/vehicle/simulation produces an `audit_log` row

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore(phase4): backend complete — all tests pass"
```
