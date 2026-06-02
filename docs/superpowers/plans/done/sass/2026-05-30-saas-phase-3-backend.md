# Phase 3 — Cadastros Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Part 2 (Frontend):** `docs/superpowers/plans/2026-05-30-saas-phase-3-frontend.md` — complete this part first.

**Goal:** Add tenant-scoped Client and Vehicle CRUD, a Postgres-backed FIPE provider chain, and CEP proxy to the FastAPI backend.

**Architecture:** Single migration 004 adds `clients`, `vehicles`, `fipe_cache` tables plus nullable FK columns on `simulations`. `PostgresFipeCache` wraps each FIPE provider (Parallelum + BrasilAPI) and stores results in Postgres with configurable TTL. `FipeService` exposes named methods (`get_brands`, `get_models`, `get_years`, `get_price`); the chain is built once at lifespan startup and stored in `app.state`. `ClientService` and `VehicleService` enforce tenant isolation and business rules at the service layer. `SimulationCreate` gains required `client_id`/`vehicle_id` fields; the service denormalizes names at save time while keeping the FK links.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, asyncpg, Pydantic v2, finacialsim_core (shared providers), loguru, pytest + testcontainers + respx

---

## File Map

**Create:**
- `backend/alembic/versions/004_cadastros.py` — migration: clients, vehicles, fipe_cache, FK cols on simulations
- `backend/finacialsim_saas/schemas/clients.py` — ClientIn, ClientOut, ClientListItem, ClientListPage
- `backend/finacialsim_saas/schemas/vehicles.py` — VehicleIn, VehicleOut, VehicleListItem, VehicleListPage, VehicleStatusUpdate
- `backend/finacialsim_saas/schemas/fipe.py` — FipeBrandItem, FipeModelItem, FipeYearItem, FipePriceOut
- `backend/finacialsim_saas/services/fipe_cache.py` — PostgresFipeCache + helpers
- `backend/finacialsim_saas/services/fipe_service.py` — build_fipe_chain, FipeService
- `backend/finacialsim_saas/services/cep_service.py` — lookup_cep
- `backend/finacialsim_saas/services/client_service.py` — ClientService
- `backend/finacialsim_saas/services/vehicle_service.py` — VehicleService
- `backend/finacialsim_saas/api/clients.py` — 5 endpoints
- `backend/finacialsim_saas/api/vehicles.py` — 6 endpoints
- `backend/finacialsim_saas/api/fipe.py` — 5 endpoints
- `backend/finacialsim_saas/api/cep.py` — 1 endpoint
- `backend/tests/test_fipe_chain.py`
- `backend/tests/test_cep_service.py`
- `backend/tests/test_client_service.py`
- `backend/tests/test_vehicle_service.py`
- `backend/tests/test_client_endpoints.py`
- `backend/tests/test_vehicle_endpoints.py`

**Modify:**
- `scripts/sync_core.py` — extend rewrite_imports + add factory.py to EXCLUDED
- `packages/finacialsim_core/finacialsim_core/integrations/fipe/parallelum.py` — fix `app.integrations.*` → `finacialsim_core.integrations.*`
- `packages/finacialsim_core/finacialsim_core/integrations/fipe/brasilapi.py` — same
- `packages/finacialsim_core/finacialsim_core/integrations/fipe/manual.py` — same
- `packages/finacialsim_core/finacialsim_core/integrations/http.py` — same
- `packages/finacialsim_core/finacialsim_core/integrations/base.py` — same (no app.* but verify)
- `backend/finacialsim_saas/data/models.py` — add Client, Vehicle, FipeCache models + Simulation FK cols
- `backend/finacialsim_saas/schemas/simulations.py` — add client_id/vehicle_id to SimulationCreate + SimulationOut
- `backend/finacialsim_saas/services/simulation_service.py` — denormalize client/vehicle names at save
- `backend/finacialsim_saas/main.py` — build fipe_chain in lifespan; include 4 new routers
- `backend/pyproject.toml` — add respx to dev deps
- `backend/tests/test_models.py` — add Phase 3 model assertions

---

## Task 1: Fix finacialsim_core integration imports

**Files:**
- Modify: `scripts/sync_core.py`
- Modify: `packages/finacialsim_core/finacialsim_core/integrations/fipe/parallelum.py`
- Modify: `packages/finacialsim_core/finacialsim_core/integrations/fipe/brasilapi.py`
- Modify: `packages/finacialsim_core/finacialsim_core/integrations/fipe/manual.py`
- Modify: `packages/finacialsim_core/finacialsim_core/integrations/http.py`

**Context:** The sync script copies FIPE/BACEN providers from the desktop repo and rewrites `from app.core.` → `from finacialsim_core.` but NOT `from app.integrations.*`. So every provider still has broken `app.integrations.*` imports. `factory.py` in the desktop also imports the SQLAlchemy-backed caches that don't exist in the saas structure — exclude it from sync entirely.

- [ ] **Step 1: Update `rewrite_imports` in sync_core.py and add `factory.py` to EXCLUDED**

```python
# scripts/sync_core.py — full replacement
#!/usr/bin/env python3
"""Sync finacialsim_core from the desktop repo.

Usage:
    FINACIALSIM_DESKTOP_PATH=/path/to/finacialsim python scripts/sync_core.py
"""
import os
import shutil
from pathlib import Path

desktop = Path(os.environ["FINACIALSIM_DESKTOP_PATH"]).resolve()
dest = Path(__file__).parent.parent / "packages" / "finacialsim_core" / "finacialsim_core"

EXCLUDED = {"cache.py", "cached.py", "factory.py", "__pycache__"}


def _ensure_init(directory: Path) -> None:
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text("")


def sync_flat(src_dir: Path, dst_dir: Path) -> None:
    """Copy *.py files from src_dir directly into dst_dir (no subdirectory)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file() and f.name not in EXCLUDED and not f.name.startswith("."):
            shutil.copy2(f, dst_dir / f.name)
            print(f"  {f.name}")


def rewrite_imports(directory: Path) -> None:
    """Rewrite app.* imports to finacialsim_core.* in all .py files under directory."""
    for f in directory.rglob("*.py"):
        text = f.read_text()
        new_text = text
        new_text = new_text.replace("from app.core.", "from finacialsim_core.")
        new_text = new_text.replace("from app.integrations.", "from finacialsim_core.integrations.")
        if new_text != text:
            f.write_text(new_text)
            print(f"  rewrote imports: {f.relative_to(directory.parent)}")


def sync_tree(src_dir: Path, dst_dir: Path) -> None:
    """Recursively copy a directory, skipping EXCLUDED files."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    _ensure_init(dst_dir)
    for item in src_dir.iterdir():
        if item.name in EXCLUDED or item.name.startswith("."):
            continue
        if item.is_dir():
            sync_tree(item, dst_dir / item.name)
        else:
            shutil.copy2(item, dst_dir / item.name)
            print(f"  {item.relative_to(src_dir.parent)}")


print("=== Syncing finacialsim_core ===")

print("\n[core] flat files:")
sync_flat(desktop / "app" / "core", dest)

print("\n[integrations]:")
sync_tree(desktop / "app" / "integrations", dest / "integrations")

print("\n[reports]:")
sync_tree(desktop / "app" / "reports", dest / "reports")

print("\n[utils]:")
(dest / "utils").mkdir(exist_ok=True)
_ensure_init(dest / "utils")
src_dv = desktop / "app" / "utils" / "document_validation.py"
if src_dv.exists():
    shutil.copy2(src_dv, dest / "utils" / "document_validation.py")
    print(f"  document_validation.py")

print("\n[tests/core]:")
tests_src = desktop / "tests" / "unit" / "core"
if tests_src.exists():
    tests_dst = Path(__file__).parent.parent / "packages" / "finacialsim_core" / "tests" / "core"
    sync_tree(tests_src, tests_dst)
    _ensure_init(tests_dst.parent)
else:
    print("  (skipped — tests/unit/core not found in source)")

print("\n[rewrite imports]:")
rewrite_imports(dest)

print("\n=== Done ===")
print(f"Destination: {dest}")
```

- [ ] **Step 2: Fix imports in the existing provider files (apply rewrite now, without running sync)**

Edit `packages/finacialsim_core/finacialsim_core/integrations/fipe/parallelum.py` — replace the three `app.` import lines:

```python
# OLD (lines 9-11):
from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote, parse_brl_price
from app.integrations.http import get_json, http_err_callback

# NEW:
from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.fipe.schema import VehicleQuote, parse_brl_price
from finacialsim_core.integrations.http import get_json, http_err_callback
```

Edit `packages/finacialsim_core/finacialsim_core/integrations/fipe/brasilapi.py` — replace:

```python
# OLD:
from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote, parse_brl_price
from app.integrations.http import get_json, http_err_callback

# NEW:
from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.fipe.schema import VehicleQuote, parse_brl_price
from finacialsim_core.integrations.http import get_json, http_err_callback
```

Edit `packages/finacialsim_core/finacialsim_core/integrations/fipe/manual.py` — replace:

```python
# OLD:
from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote

# NEW:
from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.fipe.schema import VehicleQuote
```

Edit `packages/finacialsim_core/finacialsim_core/integrations/http.py` — replace:

```python
# OLD:
from app.integrations.base import Err

# NEW:
from finacialsim_core.integrations.base import Err
```

- [ ] **Step 3: Verify imports resolve**

```bash
cd /home/fj/git/financialsim-saas
uv run --directory backend python -c "
from finacialsim_core.integrations.fipe.parallelum import ParallelumFipeProvider
from finacialsim_core.integrations.fipe.brasilapi import BrasilApiFipeProvider
from finacialsim_core.integrations.fipe.manual import ManualFipeProvider
from finacialsim_core.integrations.base import ProviderChain
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/sync_core.py \
  packages/finacialsim_core/finacialsim_core/integrations/fipe/parallelum.py \
  packages/finacialsim_core/finacialsim_core/integrations/fipe/brasilapi.py \
  packages/finacialsim_core/finacialsim_core/integrations/fipe/manual.py \
  packages/finacialsim_core/finacialsim_core/integrations/http.py
git commit -m "fix(core): rewrite app.integrations.* imports to finacialsim_core.integrations.*; exclude factory.py from sync"
```

---

## Task 2: Alembic migration 004 — Cadastros

**Files:**
- Create: `backend/alembic/versions/004_cadastros.py`

- [ ] **Step 1: Create migration file**

```python
# backend/alembic/versions/004_cadastros.py
"""cadastros — clients, vehicles, fipe_cache + FK columns on simulations

Revision ID: 004
Revises: 003
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE client_type AS ENUM ('pf', 'pj')")
    op.execute(
        "CREATE TYPE vehicle_status AS ENUM ('ativo', 'reservado', 'vendido', 'inativo')"
    )

    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("cpf_cnpj", sa.Text, nullable=False),
        sa.Column("tipo", sa.Enum("pf", "pj", name="client_type", create_type=False),
                  nullable=False),
        sa.Column("rg", sa.Text, nullable=True),
        sa.Column("data_nasc", sa.Date, nullable=True),
        sa.Column("profissao", sa.Text, nullable=True),
        sa.Column("renda", sa.Numeric(18, 2), nullable=True),
        sa.Column("telefone", sa.Text, nullable=True),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("endereco_json", JSONB, nullable=True),
        sa.Column("observacoes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("criado_por", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_clients_tenant", "clients", ["tenant_id"])
    op.create_unique_constraint(
        "uq_clients_tenant_cpf_cnpj", "clients", ["tenant_id", "cpf_cnpj"]
    )

    op.create_table(
        "vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("fonte", sa.Text, nullable=False),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("marca", sa.Text, nullable=False),
        sa.Column("modelo", sa.Text, nullable=False),
        sa.Column("ano_modelo", sa.Integer, nullable=False),
        sa.Column("combustivel", sa.Text, nullable=True),
        sa.Column("codigo_fipe", sa.Text, nullable=True),
        sa.Column("valor_fipe", sa.Numeric(18, 2), nullable=True),
        sa.Column("valor_referencia", sa.Numeric(18, 2), nullable=True),
        sa.Column("mes_referencia_fipe", sa.Text, nullable=True),
        sa.Column("cor", sa.Text, nullable=True),
        sa.Column("placa", sa.Text, nullable=True),
        sa.Column("odometro_km", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Enum("ativo", "reservado", "vendido", "inativo",
                    name="vehicle_status", create_type=False),
            nullable=False, server_default=sa.text("'ativo'"),
        ),
        sa.Column("snapshot_json", JSONB, nullable=True),
        sa.Column("criado_por", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_vehicles_tenant", "vehicles", ["tenant_id"])
    op.create_index("ix_vehicles_tenant_status", "vehicles", ["tenant_id", "status"])
    # Partial unique: only enforce unique placa within tenant when placa is not null
    op.execute(
        "CREATE UNIQUE INDEX uq_vehicles_tenant_placa "
        "ON vehicles(tenant_id, placa) WHERE placa IS NOT NULL"
    )

    op.create_table(
        "fipe_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("acao", sa.Text, nullable=False),
        sa.Column("marca_id", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("modelo_id", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("ano_id", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("ttl_horas", sa.Integer, nullable=False),
    )
    op.create_unique_constraint(
        "uq_fipe_cache_key", "fipe_cache",
        ["tipo", "acao", "marca_id", "modelo_id", "ano_id"]
    )

    # Nullable FKs on simulations — backward-compat with existing rows
    op.add_column(
        "simulations",
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id"), nullable=True),
    )
    op.add_column(
        "simulations",
        sa.Column("vehicle_id", UUID(as_uuid=True),
                  sa.ForeignKey("vehicles.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("simulations", "vehicle_id")
    op.drop_column("simulations", "client_id")
    op.drop_table("fipe_cache")
    op.drop_index("uq_vehicles_tenant_placa", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_table("clients")
    op.execute("DROP TYPE vehicle_status")
    op.execute("DROP TYPE client_type")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/004_cadastros.py
git commit -m "feat(migration): 004 — clients, vehicles, fipe_cache tables + simulation FK cols"
```

---

## Task 3: SQLAlchemy models — Client, Vehicle, FipeCache

**Files:**
- Modify: `backend/finacialsim_saas/data/models.py`

- [ ] **Step 1: Write the failing test in `backend/tests/test_models.py`**

Append to the end of the existing file:

```python
def test_all_phase3_models_importable_and_tables_exist(engine):
    from finacialsim_saas.data.models import Client, Vehicle, FipeCache
    from sqlalchemy import inspect
    import asyncio

    async def _check():
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
        return tables

    tables = asyncio.run(_check())
    assert "clients" in tables
    assert "vehicles" in tables
    assert "fipe_cache" in tables
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_models.py::test_all_phase3_models_importable_and_tables_exist -v
```

Expected: FAIL (ImportError or AssertionError — tables don't exist yet)

- [ ] **Step 3: Add models to `backend/finacialsim_saas/data/models.py`**

Append after the `ExtraordinaryAmortization` class:

```python
class ClientType(enum.Enum):
    pf = "pf"
    pj = "pj"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tipo: Mapped[ClientType] = mapped_column(
        sa.Enum(ClientType, name="client_type", native_enum=True), nullable=False
    )
    rg: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    data_nasc: Mapped[datetime | None] = mapped_column(sa.Date, nullable=True)
    profissao: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    renda: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    telefone: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    endereco_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "cpf_cnpj", name="uq_clients_tenant_cpf_cnpj"),
    )


class VehicleStatus(enum.Enum):
    ativo = "ativo"
    reservado = "reservado"
    vendido = "vendido"
    inativo = "inativo"


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    fonte: Mapped[str] = mapped_column(sa.Text, nullable=False)
    tipo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    marca: Mapped[str] = mapped_column(sa.Text, nullable=False)
    modelo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    ano_modelo: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    combustivel: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    codigo_fipe: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valor_fipe: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    valor_referencia: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2), nullable=True)
    mes_referencia_fipe: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cor: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    placa: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    odometro_km: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    status: Mapped[VehicleStatus] = mapped_column(
        sa.Enum(VehicleStatus, name="vehicle_status", native_enum=True),
        nullable=False, server_default=sa.text("'ativo'"),
    )
    snapshot_json: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.Index("ix_vehicles_tenant_status", "tenant_id", "status"),
    )


class FipeCache(Base):
    __tablename__ = "fipe_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tipo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    acao: Mapped[str] = mapped_column(sa.Text, nullable=False)
    marca_id: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    modelo_id: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    ano_id: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("''"))
    payload_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    ttl_horas: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "tipo", "acao", "marca_id", "modelo_id", "ano_id",
            name="uq_fipe_cache_key",
        ),
    )
```

Also add nullable FK columns to `Simulation`. Find the `__table_args__` in the `Simulation` class and add these two `Mapped` fields before it:

```python
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=True
    )
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_models.py -v
```

Expected: all PASS (the `engine` fixture calls `Base.metadata.create_all` which picks up the new models)

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/data/models.py backend/tests/test_models.py
git commit -m "feat(models): add Client, Vehicle, FipeCache; add client_id/vehicle_id to Simulation"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `backend/finacialsim_saas/schemas/clients.py`
- Create: `backend/finacialsim_saas/schemas/vehicles.py`
- Create: `backend/finacialsim_saas/schemas/fipe.py`
- Modify: `backend/finacialsim_saas/schemas/simulations.py`

- [ ] **Step 1: Create `backend/finacialsim_saas/schemas/clients.py`**

```python
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class ClientIn(BaseModel):
    nome: str
    cpf_cnpj: str
    tipo: str  # "pf" | "pj"
    rg: str | None = None
    data_nasc: date | None = None
    profissao: str | None = None
    renda: DecimalStr | None = None
    telefone: str | None = None
    email: str | None = None
    endereco_json: dict | None = None
    observacoes: str | None = None


class ClientOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    nome: str
    cpf_cnpj: str
    tipo: str
    rg: str | None
    data_nasc: date | None
    profissao: str | None
    renda: DecimalStr | None
    telefone: str | None
    email: str | None
    endereco_json: dict | None
    observacoes: str | None
    is_active: bool
    criado_por: uuid.UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


class ClientListItem(BaseModel):
    id: uuid.UUID
    nome: str
    cpf_cnpj: str
    tipo: str
    telefone: str | None
    email: str | None
    is_active: bool
    criado_em: datetime

    class Config:
        from_attributes = True


class ClientListPage(BaseModel):
    items: list[ClientListItem]
    next_cursor: str | None
```

- [ ] **Step 2: Create `backend/finacialsim_saas/schemas/vehicles.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class VehicleIn(BaseModel):
    fonte: str         # "fipe_parallelum" | "fipe_brasilapi" | "manual"
    tipo: str          # "carro" | "moto" | "caminhao"
    marca: str
    modelo: str
    ano_modelo: int
    combustivel: str | None = None
    codigo_fipe: str | None = None
    valor_fipe: DecimalStr | None = None
    valor_referencia: DecimalStr | None = None
    mes_referencia_fipe: str | None = None
    cor: str | None = None
    placa: str | None = None
    odometro_km: int | None = None
    snapshot_json: dict | None = None


class VehicleOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    fonte: str
    tipo: str
    marca: str
    modelo: str
    ano_modelo: int
    combustivel: str | None
    codigo_fipe: str | None
    valor_fipe: DecimalStr | None
    valor_referencia: DecimalStr | None
    mes_referencia_fipe: str | None
    cor: str | None
    placa: str | None
    odometro_km: int | None
    status: str
    snapshot_json: dict | None
    criado_por: uuid.UUID
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


class VehicleListItem(BaseModel):
    id: uuid.UUID
    tipo: str
    marca: str
    modelo: str
    ano_modelo: int
    placa: str | None
    valor_fipe: DecimalStr | None
    status: str
    criado_em: datetime

    class Config:
        from_attributes = True


class VehicleListPage(BaseModel):
    items: list[VehicleListItem]
    next_cursor: str | None


class VehicleStatusUpdate(BaseModel):
    status: str
```

- [ ] **Step 3: Create `backend/finacialsim_saas/schemas/fipe.py`**

```python
from __future__ import annotations

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class FipeBrandItem(BaseModel):
    id: str
    nome: str


class FipeModelItem(BaseModel):
    id: str
    nome: str


class FipeYearItem(BaseModel):
    id: str
    nome: str


class FipePriceOut(BaseModel):
    tipo: str
    marca: str
    marca_id: str
    modelo: str
    modelo_id: str
    ano_modelo: int
    combustivel: str
    codigo_fipe: str
    valor: DecimalStr
    mes_referencia: str
    fonte: str
```

- [ ] **Step 4: Update `backend/finacialsim_saas/schemas/simulations.py`**

Add `client_id` and `vehicle_id` (required) to `SimulationCreate`, and add them as optional to `SimulationOut` and `SimulationListItem`:

In `SimulationCreate`, add after `veiculo_descricao`:
```python
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
```

In `SimulationOut`, add after `veiculo_descricao`:
```python
    client_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
```

In `SimulationListItem`, add after `veiculo_descricao`:
```python
    client_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
```

- [ ] **Step 5: Write schema test and verify**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run python -c "
from finacialsim_saas.schemas.clients import ClientIn, ClientOut, ClientListPage
from finacialsim_saas.schemas.vehicles import VehicleIn, VehicleOut, VehicleStatusUpdate
from finacialsim_saas.schemas.fipe import FipePriceOut, FipeBrandItem
print('schemas OK')
"
```

Expected: `schemas OK`

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/schemas/clients.py \
  backend/finacialsim_saas/schemas/vehicles.py \
  backend/finacialsim_saas/schemas/fipe.py \
  backend/finacialsim_saas/schemas/simulations.py
git commit -m "feat(schemas): add Client, Vehicle, FIPE schemas; add client_id/vehicle_id to SimulationCreate"
```

---

## Task 5: PostgresFipeCache + FipeService + lifespan

**Files:**
- Create: `backend/finacialsim_saas/services/fipe_cache.py`
- Create: `backend/finacialsim_saas/services/fipe_service.py`
- Modify: `backend/finacialsim_saas/main.py`
- Modify: `backend/pyproject.toml` (add respx to dev deps)

- [ ] **Step 1: Add `respx` to dev dependencies**

In `backend/pyproject.toml`, add `"respx>=0.21.0"` to `[project.optional-dependencies] dev`:

```toml
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "respx>=0.21.0",
    "testcontainers[postgres,redis]>=4.7.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]
```

Then install:

```bash
cd /home/fj/git/financialsim-saas
uv sync --extra dev
```

- [ ] **Step 2: Create `backend/finacialsim_saas/services/fipe_cache.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from finacialsim_core.integrations.base import Err, Ok
from finacialsim_core.integrations.fipe.schema import VehicleQuote
from finacialsim_saas.data.models import FipeCache


class PostgresFipeCache:
    """Wraps a FIPE provider, caching results in the fipe_cache Postgres table."""

    def __init__(
        self,
        provider: Any,
        session_factory: async_sessionmaker,
        listas_ttl_horas: int = 720,
        preco_ttl_horas: int = 24,
    ) -> None:
        self._provider = provider
        self._sf = session_factory
        self._listas_ttl = listas_ttl_horas
        self._preco_ttl = preco_ttl_horas

    @property
    def name(self) -> str:
        return self._provider.name

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        key = _build_key(query)
        async with self._sf() as s:
            row = await _get_row(s, key)
            if row is not None and _is_fresh(row):
                logger.debug("fipe_cache_hit", provider=self.name, **key)
                return Ok(_deserialize(query.get("action", ""), row.payload_json))

        result = await self._provider.fetch(query)
        if result.is_ok:
            ttl = self._preco_ttl if query.get("action") == "price" else self._listas_ttl
            async with self._sf() as s:
                await _upsert(s, key, _serialize(query.get("action", ""), result.value), ttl)
                await s.commit()
            logger.debug("fipe_cache_miss", provider=self.name, **key)
        return result


def _build_key(query: dict) -> dict:
    return {
        "tipo": query.get("tipo", ""),
        "acao": query.get("action", ""),
        "marca_id": str(query.get("brand_id", "")),
        "modelo_id": str(query.get("model_id", "")),
        "ano_id": str(query.get("year_id", "")),
    }


def _is_fresh(row: FipeCache) -> bool:
    age_hours = (datetime.now(timezone.utc) - row.coletado_em).total_seconds() / 3600
    return age_hours < row.ttl_horas


async def _get_row(session, key: dict) -> FipeCache | None:
    stmt = select(FipeCache).where(
        FipeCache.tipo == key["tipo"],
        FipeCache.acao == key["acao"],
        FipeCache.marca_id == key["marca_id"],
        FipeCache.modelo_id == key["modelo_id"],
        FipeCache.ano_id == key["ano_id"],
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _upsert(session, key: dict, payload: dict, ttl_horas: int) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(FipeCache)
        .values(
            tipo=key["tipo"],
            acao=key["acao"],
            marca_id=key["marca_id"],
            modelo_id=key["modelo_id"],
            ano_id=key["ano_id"],
            payload_json=payload,
            coletado_em=now,
            ttl_horas=ttl_horas,
        )
        .on_conflict_do_update(
            constraint="uq_fipe_cache_key",
            set_={"payload_json": payload, "coletado_em": now, "ttl_horas": ttl_horas},
        )
    )
    await session.execute(stmt)


def _serialize(action: str, value: Any) -> dict:
    if action == "price" and isinstance(value, VehicleQuote):
        return {
            "tipo": value.tipo,
            "marca": value.marca,
            "marca_id": value.marca_id,
            "modelo": value.modelo,
            "modelo_id": value.modelo_id,
            "ano_modelo": value.ano_modelo,
            "combustivel": value.combustivel,
            "codigo_fipe": value.codigo_fipe,
            "valor": str(value.valor),
            "mes_referencia": value.mes_referencia,
            "fonte": value.fonte,
            "raw_payload": value.raw_payload,
        }
    return {"items": value}


def _deserialize(action: str, payload: dict) -> Any:
    if action == "price":
        return VehicleQuote(
            tipo=payload["tipo"],
            marca=payload["marca"],
            marca_id=payload["marca_id"],
            modelo=payload["modelo"],
            modelo_id=payload["modelo_id"],
            ano_modelo=int(payload["ano_modelo"]),
            combustivel=payload["combustivel"],
            codigo_fipe=payload["codigo_fipe"],
            valor=Decimal(payload["valor"]),
            mes_referencia=payload["mes_referencia"],
            fonte=payload["fonte"],
            raw_payload=payload.get("raw_payload", {}),
        )
    return payload["items"]
```

- [ ] **Step 3: Create `backend/finacialsim_saas/services/fipe_service.py`**

```python
from __future__ import annotations

from typing import Any

from finacialsim_core.integrations.base import ProviderChain
from finacialsim_core.integrations.fipe.brasilapi import BrasilApiFipeProvider
from finacialsim_core.integrations.fipe.parallelum import ParallelumFipeProvider
from finacialsim_core.integrations.fipe.schema import VehicleQuote
from finacialsim_saas.errors import ExternalProviderError
from finacialsim_saas.services.fipe_cache import PostgresFipeCache


def build_fipe_chain(
    session_factory,
    listas_ttl_horas: int = 720,
    preco_ttl_horas: int = 24,
) -> ProviderChain:
    parallelum = PostgresFipeCache(
        ParallelumFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    brasilapi = PostgresFipeCache(
        BrasilApiFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    return ProviderChain([parallelum, brasilapi])


class FipeService:
    def __init__(self, chain: ProviderChain) -> None:
        self._chain = chain

    async def get_brands(self, tipo: str) -> list[dict]:
        result = await self._chain.fetch({"action": "brands", "tipo": tipo})
        if result.is_err:
            raise ExternalProviderError(f"FIPE brands unavailable: {result.error}")
        return result.value

    async def get_models(self, tipo: str, brand_id: str) -> list[dict]:
        result = await self._chain.fetch(
            {"action": "models", "tipo": tipo, "brand_id": brand_id}
        )
        if result.is_err:
            raise ExternalProviderError(f"FIPE models unavailable: {result.error}")
        return result.value

    async def get_years(self, tipo: str, brand_id: str, model_id: str) -> list[dict]:
        result = await self._chain.fetch(
            {"action": "years", "tipo": tipo, "brand_id": brand_id, "model_id": model_id}
        )
        if result.is_err:
            raise ExternalProviderError(f"FIPE years unavailable: {result.error}")
        return result.value

    async def get_price(
        self, tipo: str, brand_id: str, model_id: str, year_id: str
    ) -> VehicleQuote:
        result = await self._chain.fetch(
            {
                "action": "price",
                "tipo": tipo,
                "brand_id": brand_id,
                "model_id": model_id,
                "year_id": year_id,
            }
        )
        if result.is_err:
            raise ExternalProviderError(f"FIPE price unavailable: {result.error}")
        return result.value
```

- [ ] **Step 4: Update `backend/finacialsim_saas/main.py` lifespan to build fipe_chain**

Replace the lifespan function with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.app_env)
    engine = build_engine(str(settings.database_url))
    app_state["engine"] = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.fipe_chain = build_fipe_chain(app.state.session_factory)
    logger.info("startup", env=settings.app_env, sha=settings.git_sha)
    yield
    await engine.dispose()
    logger.info("shutdown")
```

Add the import at the top of main.py:

```python
from finacialsim_saas.services.fipe_service import build_fipe_chain
```

- [ ] **Step 5: Verify startup imports work**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run python -c "
from finacialsim_saas.services.fipe_service import build_fipe_chain, FipeService
from finacialsim_saas.services.fipe_cache import PostgresFipeCache
print('fipe_service OK')
"
```

Expected: `fipe_service OK`

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/fipe_cache.py \
  backend/finacialsim_saas/services/fipe_service.py \
  backend/finacialsim_saas/main.py \
  backend/pyproject.toml
git commit -m "feat(fipe): PostgresFipeCache + FipeService + lifespan chain init"
```

---

## Task 6: CepService

**Files:**
- Create: `backend/finacialsim_saas/services/cep_service.py`

- [ ] **Step 1: Create `backend/finacialsim_saas/services/cep_service.py`**

```python
from __future__ import annotations

import httpx
from loguru import logger

BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v1/{cep}"


async def lookup_cep(cep: str) -> dict:
    """Proxy CEP lookup to BrasilAPI. Returns {} on any error (fail-open)."""
    clean = "".join(ch for ch in cep if ch.isdigit())
    if len(clean) != 8:
        return {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(BRASILAPI_CEP_URL.format(cep=clean))
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("cep_lookup_failed", cep=clean, error=str(exc))
        return {}
```

- [ ] **Step 2: Verify import**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run python -c "from finacialsim_saas.services.cep_service import lookup_cep; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/finacialsim_saas/services/cep_service.py
git commit -m "feat(cep): add lookup_cep pass-through service"
```

---

## Task 7: ClientService

**Files:**
- Create: `backend/finacialsim_saas/services/client_service.py`

- [ ] **Step 1: Write failing test in `backend/tests/test_client_service.py`**

```python
import pytest
import pytest_asyncio
import uuid
from finacialsim_saas.services.client_service import ClientService
from finacialsim_saas.schemas.clients import ClientIn
from finacialsim_saas.errors import ValidationError, ConflictError, NotFoundError, TenantAccessError
from finacialsim_saas.data.models import Role, User, Tenant
from finacialsim_saas.auth.deps import RequestContext


@pytest_asyncio.fixture
async def ctx_and_session(session):
    tenant = Tenant(name="T1", slug=f"t1-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id, email=f"u-{uuid.uuid4().hex[:6]}@t.com",
        name="U", password_hash="x", role=Role.user
    )
    session.add(user)
    await session.flush()
    ctx = RequestContext(tenant_id=tenant.id, user_id=user.id, role=Role.user)
    yield ctx, session


@pytest.mark.asyncio
async def test_create_pf_client_valid_cpf(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="João Silva", cpf_cnpj="529.982.247-25", tipo="pf")
    svc = ClientService(session)
    out = await svc.create(body, ctx)
    assert out.nome == "João Silva"
    assert out.tipo == "pf"
    assert out.tenant_id == ctx.tenant_id


@pytest.mark.asyncio
async def test_create_pf_client_invalid_cpf_raises(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="X", cpf_cnpj="111.111.111-11", tipo="pf")
    svc = ClientService(session)
    with pytest.raises(ValidationError, match="CPF"):
        await svc.create(body, ctx)


@pytest.mark.asyncio
async def test_create_pj_client_valid_cnpj(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="Empresa X", cpf_cnpj="11.222.333/0001-81", tipo="pj")
    svc = ClientService(session)
    out = await svc.create(body, ctx)
    assert out.tipo == "pj"


@pytest.mark.asyncio
async def test_duplicate_cpf_cnpj_raises_conflict(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="A", cpf_cnpj="529.982.247-25", tipo="pf")
    svc = ClientService(session)
    await svc.create(body, ctx)
    with pytest.raises(ConflictError):
        await svc.create(ClientIn(nome="B", cpf_cnpj="529.982.247-25", tipo="pf"), ctx)


@pytest.mark.asyncio
async def test_cross_tenant_get_raises_403(ctx_and_session, session):
    ctx, _ = ctx_and_session
    other_tenant = Tenant(name="T2", slug=f"t2-{uuid.uuid4().hex[:6]}")
    session.add(other_tenant)
    await session.flush()
    other_user = User(
        tenant_id=other_tenant.id, email=f"o-{uuid.uuid4().hex[:6]}@t.com",
        name="O", password_hash="x", role=Role.user
    )
    session.add(other_user)
    await session.flush()

    body = ClientIn(nome="A", cpf_cnpj="529.982.247-25", tipo="pf")
    svc_a = ClientService(session)
    created = await svc_a.create(body, ctx)

    other_ctx = RequestContext(tenant_id=other_tenant.id, user_id=other_user.id, role=Role.user)
    svc_b = ClientService(session)
    with pytest.raises(TenantAccessError):
        await svc_b.get(created.id, other_ctx)


@pytest.mark.asyncio
async def test_deactivate_client(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="A", cpf_cnpj="529.982.247-25", tipo="pf")
    svc = ClientService(session)
    created = await svc.create(body, ctx)
    out = await svc.deactivate(created.id, ctx)
    assert out.is_active is False
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_client_service.py -v
```

Expected: FAIL (ImportError — ClientService not yet created)

- [ ] **Step 3: Create `backend/finacialsim_saas/services/client_service.py`**

```python
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_core.utils.document_validation import is_valid_cnpj, is_valid_cpf
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Client, ClientType
from finacialsim_saas.errors import ConflictError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.clients import ClientIn, ClientListItem, ClientListPage, ClientOut


class ClientService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, body: ClientIn, ctx: RequestContext) -> ClientOut:
        _validate_document(body.cpf_cnpj, body.tipo)
        existing = (
            await self._s.execute(
                select(Client).where(
                    Client.tenant_id == ctx.tenant_id,
                    Client.cpf_cnpj == body.cpf_cnpj,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Cliente com CPF/CNPJ {body.cpf_cnpj} já existe")

        client = Client(
            tenant_id=ctx.tenant_id,
            nome=body.nome,
            cpf_cnpj=body.cpf_cnpj,
            tipo=ClientType(body.tipo),
            rg=body.rg,
            data_nasc=body.data_nasc,
            profissao=body.profissao,
            renda=body.renda,
            telefone=body.telefone,
            email=body.email,
            endereco_json=body.endereco_json,
            observacoes=body.observacoes,
            criado_por=ctx.user_id,
        )
        self._s.add(client)
        await self._s.flush()
        return _to_out(client)

    async def get(self, client_id: uuid.UUID, ctx: RequestContext) -> ClientOut:
        return _to_out(await self._get_or_404(client_id, ctx.tenant_id))

    async def list(
        self,
        ctx: RequestContext,
        q: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ClientListPage:
        stmt = select(Client).where(
            Client.tenant_id == ctx.tenant_id,
            Client.is_active.is_(True),
        )
        if q:
            stmt = stmt.where(
                Client.nome.ilike(f"%{q}%") | Client.cpf_cnpj.ilike(f"%{q}%")
            )
        if cursor:
            stmt = stmt.where(Client.criado_em < _decode_cursor(cursor))
        stmt = stmt.order_by(Client.criado_em.desc()).limit(limit + 1)

        rows = (await self._s.execute(stmt)).scalars().all()
        next_cursor = None
        if len(rows) > limit:
            rows = list(rows[:limit])
            next_cursor = _encode_cursor(rows[-1].criado_em)

        return ClientListPage(
            items=[_to_list_item(r) for r in rows],
            next_cursor=next_cursor,
        )

    async def update(self, client_id: uuid.UUID, body: ClientIn, ctx: RequestContext) -> ClientOut:
        client = await self._get_or_404(client_id, ctx.tenant_id)
        _validate_document(body.cpf_cnpj, body.tipo)
        if body.cpf_cnpj != client.cpf_cnpj:
            dupe = (
                await self._s.execute(
                    select(Client).where(
                        Client.tenant_id == ctx.tenant_id,
                        Client.cpf_cnpj == body.cpf_cnpj,
                    )
                )
            ).scalar_one_or_none()
            if dupe is not None:
                raise ConflictError(f"CPF/CNPJ {body.cpf_cnpj} já em uso")
        client.nome = body.nome
        client.cpf_cnpj = body.cpf_cnpj
        client.tipo = ClientType(body.tipo)
        client.rg = body.rg
        client.data_nasc = body.data_nasc
        client.profissao = body.profissao
        client.renda = body.renda
        client.telefone = body.telefone
        client.email = body.email
        client.endereco_json = body.endereco_json
        client.observacoes = body.observacoes
        client.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(client)

    async def deactivate(self, client_id: uuid.UUID, ctx: RequestContext) -> ClientOut:
        client = await self._get_or_404(client_id, ctx.tenant_id)
        client.is_active = False
        client.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(client)

    async def _get_or_404(self, client_id: uuid.UUID, tenant_id: uuid.UUID) -> Client:
        row = await self._s.get(Client, client_id)
        if row is None:
            raise NotFoundError(f"Cliente {client_id} não encontrado")
        if row.tenant_id != tenant_id:
            raise TenantAccessError("Acesso negado")
        return row


def _validate_document(cpf_cnpj: str, tipo: str) -> None:
    clean = "".join(ch for ch in cpf_cnpj if ch.isdigit())
    if tipo == "pf":
        if not is_valid_cpf(clean):
            raise ValidationError("CPF inválido")
    elif tipo == "pj":
        if not is_valid_cnpj(clean):
            raise ValidationError("CNPJ inválido")
    else:
        raise ValidationError(f"tipo inválido: {tipo!r}. Use 'pf' ou 'pj'")


def _encode_cursor(dt: datetime) -> str:
    return base64.b64encode(dt.isoformat().encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    return datetime.fromisoformat(base64.b64decode(cursor).decode())


def _to_out(c: Client) -> ClientOut:
    return ClientOut(
        id=c.id,
        tenant_id=c.tenant_id,
        nome=c.nome,
        cpf_cnpj=c.cpf_cnpj,
        tipo=c.tipo.value,
        rg=c.rg,
        data_nasc=c.data_nasc,
        profissao=c.profissao,
        renda=c.renda,
        telefone=c.telefone,
        email=c.email,
        endereco_json=c.endereco_json,
        observacoes=c.observacoes,
        is_active=c.is_active,
        criado_por=c.criado_por,
        criado_em=c.criado_em,
        atualizado_em=c.atualizado_em,
    )


def _to_list_item(c: Client) -> ClientListItem:
    return ClientListItem(
        id=c.id,
        nome=c.nome,
        cpf_cnpj=c.cpf_cnpj,
        tipo=c.tipo.value,
        telefone=c.telefone,
        email=c.email,
        is_active=c.is_active,
        criado_em=c.criado_em,
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_client_service.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/client_service.py \
  backend/tests/test_client_service.py
git commit -m "feat(clients): add ClientService with mod-11 validation + tenant isolation"
```

---

## Task 8: VehicleService

**Files:**
- Create: `backend/finacialsim_saas/services/vehicle_service.py`
- Create: `backend/tests/test_vehicle_service.py`

- [ ] **Step 1: Write failing test in `backend/tests/test_vehicle_service.py`**

```python
import pytest
import pytest_asyncio
import uuid
from decimal import Decimal

from finacialsim_saas.services.vehicle_service import VehicleService
from finacialsim_saas.schemas.vehicles import VehicleIn
from finacialsim_saas.errors import ValidationError, NotFoundError, TenantAccessError
from finacialsim_saas.data.models import Role, User, Tenant
from finacialsim_saas.auth.deps import RequestContext


@pytest_asyncio.fixture
async def ctx_and_session(session):
    tenant = Tenant(name="T", slug=f"tv-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id, email=f"vu-{uuid.uuid4().hex[:6]}@t.com",
        name="U", password_hash="x", role=Role.user
    )
    session.add(user)
    await session.flush()
    yield RequestContext(tenant_id=tenant.id, user_id=user.id, role=Role.user), session


def _fipe_body(**kwargs) -> VehicleIn:
    return VehicleIn(
        fonte="fipe_parallelum",
        tipo="carro",
        marca="Toyota",
        modelo="Corolla",
        ano_modelo=2023,
        codigo_fipe="005004-4",
        valor_fipe="120000.00",
        mes_referencia_fipe="maio/2026",
        snapshot_json={"marca_id": "21", "modelo_id": "4591", "year_id": "2023-1"},
        **kwargs,
    )


@pytest.mark.asyncio
async def test_create_vehicle_defaults_to_ativo(ctx_and_session):
    ctx, session = ctx_and_session
    out = await VehicleService(session).create(_fipe_body(), ctx)
    assert out.status == "ativo"
    assert out.tenant_id == ctx.tenant_id


@pytest.mark.asyncio
async def test_set_status_ativo_to_reservado(ctx_and_session):
    ctx, session = ctx_and_session
    svc = VehicleService(session)
    v = await svc.create(_fipe_body(), ctx)
    out = await svc.set_status(v.id, "reservado", ctx)
    assert out.status == "reservado"


@pytest.mark.asyncio
async def test_set_status_vendido_to_ativo_raises(ctx_and_session):
    ctx, session = ctx_and_session
    svc = VehicleService(session)
    v = await svc.create(_fipe_body(), ctx)
    await svc.set_status(v.id, "reservado", ctx)
    await svc.set_status(v.id, "vendido", ctx)
    with pytest.raises(ValidationError, match="Transição"):
        await svc.set_status(v.id, "ativo", ctx)


@pytest.mark.asyncio
async def test_refresh_fipe_manual_vehicle_raises(ctx_and_session):
    ctx, session = ctx_and_session
    body = VehicleIn(
        fonte="manual", tipo="carro", marca="Honda", modelo="Fit", ano_modelo=2020
    )
    svc = VehicleService(session)
    v = await svc.create(body, ctx)
    with pytest.raises(ValidationError, match="manual"):
        await svc.refresh_fipe(v.id, ctx)


@pytest.mark.asyncio
async def test_cross_tenant_access_raises(ctx_and_session, session):
    ctx, _ = ctx_and_session
    other_tenant = Tenant(name="T2", slug=f"tv2-{uuid.uuid4().hex[:6]}")
    session.add(other_tenant)
    await session.flush()
    other_user = User(
        tenant_id=other_tenant.id, email=f"vu2-{uuid.uuid4().hex[:6]}@t.com",
        name="U2", password_hash="x", role=Role.user
    )
    session.add(other_user)
    await session.flush()

    svc_a = VehicleService(session)
    v = await svc_a.create(_fipe_body(), ctx)

    other_ctx = RequestContext(
        tenant_id=other_tenant.id, user_id=other_user.id, role=Role.user
    )
    with pytest.raises(TenantAccessError):
        await VehicleService(session).get(v.id, other_ctx)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_vehicle_service.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Create `backend/finacialsim_saas/services/vehicle_service.py`**

```python
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Vehicle, VehicleStatus
from finacialsim_saas.errors import ExternalProviderError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.vehicles import VehicleIn, VehicleListItem, VehicleListPage, VehicleOut

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "ativo": {"reservado", "inativo"},
    "inativo": {"ativo"},
    "reservado": {"vendido", "ativo"},
    "vendido": set(),
}


class VehicleService:
    def __init__(self, session: AsyncSession, fipe_chain: Any = None) -> None:
        self._s = session
        self._fipe = fipe_chain

    async def create(self, body: VehicleIn, ctx: RequestContext) -> VehicleOut:
        vehicle = Vehicle(
            tenant_id=ctx.tenant_id,
            fonte=body.fonte,
            tipo=body.tipo,
            marca=body.marca,
            modelo=body.modelo,
            ano_modelo=body.ano_modelo,
            combustivel=body.combustivel,
            codigo_fipe=body.codigo_fipe,
            valor_fipe=Decimal(str(body.valor_fipe)) if body.valor_fipe is not None else None,
            valor_referencia=Decimal(str(body.valor_referencia)) if body.valor_referencia is not None else None,
            mes_referencia_fipe=body.mes_referencia_fipe,
            cor=body.cor,
            placa=body.placa,
            odometro_km=body.odometro_km,
            snapshot_json=body.snapshot_json,
            status=VehicleStatus.ativo,
            criado_por=ctx.user_id,
        )
        self._s.add(vehicle)
        await self._s.flush()
        return _to_out(vehicle)

    async def get(self, vehicle_id: uuid.UUID, ctx: RequestContext) -> VehicleOut:
        return _to_out(await self._get_or_404(vehicle_id, ctx.tenant_id))

    async def list(
        self,
        ctx: RequestContext,
        status: str | None = None,
        placa: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> VehicleListPage:
        stmt = select(Vehicle).where(Vehicle.tenant_id == ctx.tenant_id)
        if status:
            stmt = stmt.where(Vehicle.status == VehicleStatus(status))
        if placa:
            stmt = stmt.where(Vehicle.placa.ilike(f"%{placa}%"))
        if cursor:
            stmt = stmt.where(Vehicle.criado_em < _decode_cursor(cursor))
        stmt = stmt.order_by(Vehicle.criado_em.desc()).limit(limit + 1)

        rows = (await self._s.execute(stmt)).scalars().all()
        next_cursor = None
        if len(rows) > limit:
            rows = list(rows[:limit])
            next_cursor = _encode_cursor(rows[-1].criado_em)

        return VehicleListPage(
            items=[_to_list_item(r) for r in rows],
            next_cursor=next_cursor,
        )

    async def update(self, vehicle_id: uuid.UUID, body: VehicleIn, ctx: RequestContext) -> VehicleOut:
        v = await self._get_or_404(vehicle_id, ctx.tenant_id)
        v.fonte = body.fonte
        v.tipo = body.tipo
        v.marca = body.marca
        v.modelo = body.modelo
        v.ano_modelo = body.ano_modelo
        v.combustivel = body.combustivel
        v.codigo_fipe = body.codigo_fipe
        v.valor_fipe = Decimal(str(body.valor_fipe)) if body.valor_fipe is not None else None
        v.valor_referencia = Decimal(str(body.valor_referencia)) if body.valor_referencia is not None else None
        v.mes_referencia_fipe = body.mes_referencia_fipe
        v.cor = body.cor
        v.placa = body.placa
        v.odometro_km = body.odometro_km
        v.snapshot_json = body.snapshot_json
        v.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(v)

    async def set_status(self, vehicle_id: uuid.UUID, new_status: str, ctx: RequestContext) -> VehicleOut:
        v = await self._get_or_404(vehicle_id, ctx.tenant_id)
        current = v.status.value
        allowed = _VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Transição {current!r} → {new_status!r} não permitida. "
                f"Permitidas: {sorted(allowed) or 'nenhuma'}"
            )
        v.status = VehicleStatus(new_status)
        v.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(v)

    async def refresh_fipe(self, vehicle_id: uuid.UUID, ctx: RequestContext) -> VehicleOut:
        if self._fipe is None:
            raise RuntimeError("fipe_chain not injected into VehicleService")
        v = await self._get_or_404(vehicle_id, ctx.tenant_id)
        if v.fonte == "manual":
            raise ValidationError("Veículo manual não tem dados FIPE para atualizar")
        snap = v.snapshot_json or {}
        result = await self._fipe.fetch({
            "action": "price",
            "tipo": v.tipo,
            "brand_id": snap.get("marca_id", ""),
            "model_id": snap.get("modelo_id", ""),
            "year_id": snap.get("year_id", ""),
        })
        if result.is_err:
            raise ExternalProviderError(f"FIPE unavailable: {result.error}")
        quote = result.value
        v.valor_fipe = quote.valor
        v.mes_referencia_fipe = quote.mes_referencia
        v.snapshot_json = {
            **snap,
            **quote.raw_payload,
            "marca_id": quote.marca_id,
            "modelo_id": quote.modelo_id,
        }
        v.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(v)

    async def _get_or_404(self, vehicle_id: uuid.UUID, tenant_id: uuid.UUID) -> Vehicle:
        row = await self._s.get(Vehicle, vehicle_id)
        if row is None:
            raise NotFoundError(f"Veículo {vehicle_id} não encontrado")
        if row.tenant_id != tenant_id:
            raise TenantAccessError("Acesso negado")
        return row


def _encode_cursor(dt: datetime) -> str:
    return base64.b64encode(dt.isoformat().encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    return datetime.fromisoformat(base64.b64decode(cursor).decode())


def _to_out(v: Vehicle) -> VehicleOut:
    return VehicleOut(
        id=v.id,
        tenant_id=v.tenant_id,
        fonte=v.fonte,
        tipo=v.tipo,
        marca=v.marca,
        modelo=v.modelo,
        ano_modelo=v.ano_modelo,
        combustivel=v.combustivel,
        codigo_fipe=v.codigo_fipe,
        valor_fipe=v.valor_fipe,
        valor_referencia=v.valor_referencia,
        mes_referencia_fipe=v.mes_referencia_fipe,
        cor=v.cor,
        placa=v.placa,
        odometro_km=v.odometro_km,
        status=v.status.value,
        snapshot_json=v.snapshot_json,
        criado_por=v.criado_por,
        criado_em=v.criado_em,
        atualizado_em=v.atualizado_em,
    )


def _to_list_item(v: Vehicle) -> VehicleListItem:
    return VehicleListItem(
        id=v.id,
        tipo=v.tipo,
        marca=v.marca,
        modelo=v.modelo,
        ano_modelo=v.ano_modelo,
        placa=v.placa,
        valor_fipe=v.valor_fipe,
        status=v.status.value,
        criado_em=v.criado_em,
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_vehicle_service.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/vehicle_service.py \
  backend/tests/test_vehicle_service.py
git commit -m "feat(vehicles): add VehicleService with status transitions and FIPE refresh"
```

---

## Task 9: Update SimulationService + API endpoints + register routers

**Files:**
- Modify: `backend/finacialsim_saas/services/simulation_service.py`
- Create: `backend/finacialsim_saas/api/clients.py`
- Create: `backend/finacialsim_saas/api/vehicles.py`
- Create: `backend/finacialsim_saas/api/fipe.py`
- Create: `backend/finacialsim_saas/api/cep.py`
- Modify: `backend/finacialsim_saas/main.py`

- [ ] **Step 1: Update SimulationService to denormalize client/vehicle names**

In `backend/finacialsim_saas/services/simulation_service.py`, find the `create` method's section that builds the `Simulation` object. Add lookups for `client_id` and `vehicle_id`:

After the `_compute(...)` call and before constructing `sim = Simulation(...)`, add:

```python
        # Resolve client/vehicle names for denormalized display fields
        from finacialsim_saas.data.models import Client, Vehicle
        client_row = await session.get(Client, body.client_id)
        if client_row is None or client_row.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"Cliente {body.client_id} não encontrado")
        vehicle_row = await session.get(Vehicle, body.vehicle_id)
        if vehicle_row is None or vehicle_row.tenant_id != ctx.tenant_id:
            raise NotFoundError(f"Veículo {body.vehicle_id} não encontrado")
        cliente_nome = client_row.nome
        veiculo_descricao = f"{vehicle_row.marca} {vehicle_row.modelo} {vehicle_row.ano_modelo}"
```

Then update the `Simulation(...)` constructor to include:

```python
            client_id=body.client_id,
            vehicle_id=body.vehicle_id,
            cliente_nome=cliente_nome,
            veiculo_descricao=veiculo_descricao,
```

And remove the old `cliente_nome=body.cliente_nome, veiculo_descricao=body.veiculo_descricao` lines.

Also add `client_id` and `vehicle_id` to `SimulationOut` mapping (in `_to_out` or wherever the service maps the model to the schema). Add:

```python
        client_id=sim.client_id,
        vehicle_id=sim.vehicle_id,
```

- [ ] **Step 2: Create `backend/finacialsim_saas/api/clients.py`**

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.clients import ClientIn, ClientListPage, ClientOut
from finacialsim_saas.services.client_service import ClientService

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


@router.get("", response_model=ClientListPage)
async def list_clients(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> ClientListPage:
    return await ClientService(session).list(ctx, q=q, cursor=cursor, limit=limit)


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    body: ClientIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    result = await ClientService(session).create(body, ctx)
    await session.commit()
    return result


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    return await ClientService(session).get(client_id, ctx)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID,
    body: ClientIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    result = await ClientService(session).update(client_id, body, ctx)
    await session.commit()
    return result


@router.post("/{client_id}/deactivate", response_model=ClientOut)
async def deactivate_client(
    client_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    result = await ClientService(session).deactivate(client_id, ctx)
    await session.commit()
    return result
```

- [ ] **Step 3: Create `backend/finacialsim_saas/api/vehicles.py`**

```python
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.vehicles import VehicleIn, VehicleListPage, VehicleOut, VehicleStatusUpdate
from finacialsim_saas.services.vehicle_service import VehicleService

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


@router.get("", response_model=VehicleListPage)
async def list_vehicles(
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    placa: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> VehicleListPage:
    fipe_chain = getattr(request.app.state, "fipe_chain", None)
    return await VehicleService(session, fipe_chain).list(
        ctx, status=status, placa=placa, cursor=cursor, limit=limit
    )


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    body: VehicleIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    result = await VehicleService(session).create(body, ctx)
    await session.commit()
    return result


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    return await VehicleService(session).get(vehicle_id, ctx)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    result = await VehicleService(session).update(vehicle_id, body, ctx)
    await session.commit()
    return result


@router.post("/{vehicle_id}/refresh-fipe", response_model=VehicleOut)
async def refresh_fipe(
    vehicle_id: uuid.UUID,
    request: Request,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    fipe_chain = request.app.state.fipe_chain
    result = await VehicleService(session, fipe_chain).refresh_fipe(vehicle_id, ctx)
    await session.commit()
    return result


@router.post("/{vehicle_id}/status", response_model=VehicleOut)
async def set_vehicle_status(
    vehicle_id: uuid.UUID,
    body: VehicleStatusUpdate,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VehicleOut:
    result = await VehicleService(session).set_status(vehicle_id, body.status, ctx)
    await session.commit()
    return result
```

- [ ] **Step 4: Create `backend/finacialsim_saas/api/fipe.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx
from finacialsim_saas.schemas.fipe import FipeBrandItem, FipeModelItem, FipePriceOut, FipeYearItem
from finacialsim_saas.services.fipe_service import FipeService

router = APIRouter(prefix="/api/v1/fipe", tags=["fipe"])

_VALID_TIPOS = {"carro", "moto", "caminhao"}


@router.get("/types")
async def get_fipe_types(
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
) -> list[str]:
    return list(_VALID_TIPOS)


@router.get("/brands", response_model=list[FipeBrandItem])
async def get_brands(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
) -> list[FipeBrandItem]:
    svc = FipeService(request.app.state.fipe_chain)
    return [FipeBrandItem(**b) for b in await svc.get_brands(tipo)]


@router.get("/models", response_model=list[FipeModelItem])
async def get_models(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
    brand_id: str = Query(...),
) -> list[FipeModelItem]:
    svc = FipeService(request.app.state.fipe_chain)
    return [FipeModelItem(**m) for m in await svc.get_models(tipo, brand_id)]


@router.get("/years", response_model=list[FipeYearItem])
async def get_years(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
    brand_id: str = Query(...),
    model_id: str = Query(...),
) -> list[FipeYearItem]:
    svc = FipeService(request.app.state.fipe_chain)
    return [FipeYearItem(**y) for y in await svc.get_years(tipo, brand_id, model_id)]


@router.get("/price", response_model=FipePriceOut)
async def get_price(
    request: Request,
    _ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    tipo: str = Query(...),
    brand_id: str = Query(...),
    model_id: str = Query(...),
    year_id: str = Query(...),
) -> FipePriceOut:
    svc = FipeService(request.app.state.fipe_chain)
    quote = await svc.get_price(tipo, brand_id, model_id, year_id)
    return FipePriceOut(
        tipo=quote.tipo,
        marca=quote.marca,
        marca_id=quote.marca_id,
        modelo=quote.modelo,
        modelo_id=quote.modelo_id,
        ano_modelo=quote.ano_modelo,
        combustivel=quote.combustivel,
        codigo_fipe=quote.codigo_fipe,
        valor=quote.valor,
        mes_referencia=quote.mes_referencia,
        fonte=quote.fonte,
    )
```

- [ ] **Step 5: Create `backend/finacialsim_saas/api/cep.py`**

```python
from fastapi import APIRouter

from finacialsim_saas.services.cep_service import lookup_cep

router = APIRouter(prefix="/api/v1/cep", tags=["cep"])


@router.get("/{cep}")
async def get_cep(cep: str) -> dict:
    return await lookup_cep(cep)
```

- [ ] **Step 6: Register new routers in `backend/finacialsim_saas/main.py`**

Append after the existing router imports and `app.include_router` calls:

```python
from finacialsim_saas.api.clients import router as clients_router          # noqa: E402
from finacialsim_saas.api.vehicles import router as vehicles_router        # noqa: E402
from finacialsim_saas.api.fipe import router as fipe_router                # noqa: E402
from finacialsim_saas.api.cep import router as cep_router                  # noqa: E402

app.include_router(clients_router)
app.include_router(vehicles_router)
app.include_router(fipe_router)
app.include_router(cep_router)
```

- [ ] **Step 7: Smoke-test import chain**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run python -c "from finacialsim_saas.main import app; print('app OK')"
```

Expected: `app OK`

- [ ] **Step 8: Commit**

```bash
git add backend/finacialsim_saas/services/simulation_service.py \
  backend/finacialsim_saas/api/clients.py \
  backend/finacialsim_saas/api/vehicles.py \
  backend/finacialsim_saas/api/fipe.py \
  backend/finacialsim_saas/api/cep.py \
  backend/finacialsim_saas/main.py
git commit -m "feat(api): add clients, vehicles, fipe, cep endpoints; SimulationService denormalizes client/vehicle names"
```

---

## Task 10: Backend tests — FIPE chain + CEP

**Files:**
- Create: `backend/tests/test_fipe_chain.py`
- Create: `backend/tests/test_cep_service.py`

- [ ] **Step 1: Create `backend/tests/test_fipe_chain.py`**

Uses `unittest.mock.AsyncMock` to mock providers — no real HTTP, no real DB.

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from finacialsim_core.integrations.base import Err, Ok, ProviderChain
from finacialsim_core.integrations.fipe.schema import VehicleQuote
from finacialsim_saas.services.fipe_cache import PostgresFipeCache


def _mock_session_factory(cached_row=None):
    """Returns a session_factory whose sessions return cached_row on SELECT."""
    mock_session = AsyncMock()
    mock_execute = AsyncMock()
    mock_execute.scalar_one_or_none = MagicMock(return_value=cached_row)
    mock_session.execute = AsyncMock(return_value=mock_execute)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock()
    factory.return_value = mock_session
    return factory, mock_session


@pytest.mark.asyncio
async def test_primary_ok_returns_value():
    factory, _ = _mock_session_factory(cached_row=None)
    provider = AsyncMock()
    brands = [{"id": "21", "nome": "Toyota"}]
    provider.fetch = AsyncMock(return_value=Ok(brands))
    provider.name = "fipe_parallelum"

    cache = PostgresFipeCache(provider, factory)
    result = await cache.fetch({"action": "brands", "tipo": "carro"})

    assert result.is_ok
    assert result.value == brands


@pytest.mark.asyncio
async def test_primary_fail_fallback_ok():
    factory, _ = _mock_session_factory(cached_row=None)
    primary = AsyncMock()
    primary.fetch = AsyncMock(return_value=Err("timeout"))
    primary.name = "fipe_parallelum"
    secondary = AsyncMock()
    brands = [{"id": "21", "nome": "Toyota"}]
    secondary.fetch = AsyncMock(return_value=Ok(brands))
    secondary.name = "fipe_brasilapi"

    p_cache = PostgresFipeCache(primary, factory)
    s_cache = PostgresFipeCache(secondary, factory)
    chain = ProviderChain([p_cache, s_cache])

    result = await chain.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_ok
    assert result.value == brands


@pytest.mark.asyncio
async def test_cache_hit_skips_provider():
    from datetime import datetime, timezone
    from finacialsim_saas.data.models import FipeCache

    cached = FipeCache.__new__(FipeCache)
    cached.payload_json = {"items": [{"id": "21", "nome": "Toyota"}]}
    cached.coletado_em = datetime.now(timezone.utc)
    cached.ttl_horas = 720

    factory, _ = _mock_session_factory(cached_row=cached)
    provider = AsyncMock()
    provider.name = "fipe_parallelum"

    cache = PostgresFipeCache(provider, factory)
    result = await cache.fetch({"action": "brands", "tipo": "carro"})

    assert result.is_ok
    provider.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_both_fail_returns_err():
    factory, _ = _mock_session_factory(cached_row=None)
    primary = AsyncMock()
    primary.fetch = AsyncMock(return_value=Err("timeout"))
    primary.name = "fipe_parallelum"
    secondary = AsyncMock()
    secondary.fetch = AsyncMock(return_value=Err("500"))
    secondary.name = "fipe_brasilapi"

    p_cache = PostgresFipeCache(primary, factory)
    s_cache = PostgresFipeCache(secondary, factory)
    chain = ProviderChain([p_cache, s_cache])

    result = await chain.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_err


@pytest.mark.asyncio
async def test_price_serialization_roundtrip():
    from finacialsim_saas.services.fipe_cache import _serialize, _deserialize
    quote = VehicleQuote(
        tipo="carro", marca="Toyota", marca_id="21",
        modelo="Corolla", modelo_id="4591", ano_modelo=2023,
        combustivel="Gasolina", codigo_fipe="005004-4",
        valor=Decimal("120000.00"), mes_referencia="maio/2026",
        fonte="fipe_parallelum", raw_payload={"price": "R$ 120.000,00"},
    )
    serialized = _serialize("price", quote)
    deserialized = _deserialize("price", serialized)
    assert deserialized.valor == Decimal("120000.00")
    assert deserialized.marca == "Toyota"
```

- [ ] **Step 2: Create `backend/tests/test_cep_service.py`**

```python
import pytest
import respx
import httpx

from finacialsim_saas.services.cep_service import lookup_cep


@pytest.mark.asyncio
@respx.mock
async def test_cep_lookup_returns_brasilapi_response():
    respx.get("https://brasilapi.com.br/api/cep/v1/01310100").mock(
        return_value=httpx.Response(
            200,
            json={
                "cep": "01310100",
                "logradouro": "Av. Paulista",
                "complemento": "",
                "bairro": "Bela Vista",
                "localidade": "São Paulo",
                "uf": "SP",
            },
        )
    )
    result = await lookup_cep("01310-100")
    assert result["cep"] == "01310100"
    assert result["uf"] == "SP"


@pytest.mark.asyncio
@respx.mock
async def test_cep_lookup_fails_open_on_error():
    respx.get("https://brasilapi.com.br/api/cep/v1/99999999").mock(
        return_value=httpx.Response(404)
    )
    result = await lookup_cep("99999-999")
    assert result == {}


@pytest.mark.asyncio
async def test_cep_invalid_length_returns_empty():
    result = await lookup_cep("123")
    assert result == {}
```

- [ ] **Step 3: Run tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_fipe_chain.py tests/test_cep_service.py -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_fipe_chain.py backend/tests/test_cep_service.py
git commit -m "test(fipe,cep): FIPE chain mock tests + CEP fail-open tests"
```

---

## Task 11: Backend tests — Client + Vehicle endpoints

**Files:**
- Create: `backend/tests/test_client_endpoints.py`
- Create: `backend/tests/test_vehicle_endpoints.py`

- [ ] **Step 1: Create `backend/tests/test_client_endpoints.py`**

```python
import pytest
import uuid
from finacialsim_saas.data.models import Tenant, User, Role
from finacialsim_saas.auth.service import AuthService


async def _seed(session):
    tenant = Tenant(name="CT", slug=f"ct-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    svc = AuthService(session)
    email = f"ct-{uuid.uuid4().hex[:6]}@t.com"
    user = await svc.register_user(
        tenant_id=tenant.id, email=email, name="U",
        password="pass123!", role=Role.manager
    )
    await session.commit()
    return tenant, user, email


@pytest.mark.asyncio
async def test_create_and_get_client(client, session):
    tenant, _user, email = await _seed(session)
    tokens = (await client.post("/api/v1/auth/login", json={"email": email, "password": "pass123!"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post(
        "/api/v1/clients",
        json={"nome": "João Silva", "cpf_cnpj": "529.982.247-25", "tipo": "pf"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["nome"] == "João Silva"

    resp2 = await client.get(f"/api/v1/clients/{data['id']}", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == data["id"]


@pytest.mark.asyncio
async def test_create_client_invalid_cpf_returns_422(client, session):
    tenant, _user, email = await _seed(session)
    tokens = (await client.post("/api/v1/auth/login", json={"email": email, "password": "pass123!"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post(
        "/api/v1/clients",
        json={"nome": "X", "cpf_cnpj": "111.111.111-11", "tipo": "pf"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_deactivate_client(client, session):
    tenant, _user, email = await _seed(session)
    tokens = (await client.post("/api/v1/auth/login", json={"email": email, "password": "pass123!"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    create_resp = await client.post(
        "/api/v1/clients",
        json={"nome": "João", "cpf_cnpj": "529.982.247-25", "tipo": "pf"},
        headers=headers,
    )
    cid = create_resp.json()["id"]
    deact = await client.post(f"/api/v1/clients/{cid}/deactivate", headers=headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False


@pytest.mark.asyncio
async def test_cross_tenant_client_returns_403(client, session):
    t1, _, e1 = await _seed(session)
    t2, _, e2 = await _seed(session)
    tok1 = (await client.post("/api/v1/auth/login", json={"email": e1, "password": "pass123!"})).json()
    tok2 = (await client.post("/api/v1/auth/login", json={"email": e2, "password": "pass123!"})).json()
    h1 = {"Authorization": f"Bearer {tok1['access_token']}"}
    h2 = {"Authorization": f"Bearer {tok2['access_token']}"}

    c_resp = await client.post(
        "/api/v1/clients",
        json={"nome": "T1 Client", "cpf_cnpj": "529.982.247-25", "tipo": "pf"},
        headers=h1,
    )
    cid = c_resp.json()["id"]
    resp = await client.get(f"/api/v1/clients/{cid}", headers=h2)
    assert resp.status_code == 403
```

- [ ] **Step 2: Create `backend/tests/test_vehicle_endpoints.py`**

```python
import pytest
import uuid
from finacialsim_saas.data.models import Tenant, User, Role
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.main import app


async def _seed(session):
    tenant = Tenant(name="VT", slug=f"vt-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    svc = AuthService(session)
    email = f"vt-{uuid.uuid4().hex[:6]}@t.com"
    await svc.register_user(
        tenant_id=tenant.id, email=email, name="U",
        password="pass123!", role=Role.manager
    )
    await session.commit()
    return tenant, email


_VEHICLE_BODY = {
    "fonte": "fipe_parallelum",
    "tipo": "carro",
    "marca": "Toyota",
    "modelo": "Corolla",
    "ano_modelo": 2023,
    "codigo_fipe": "005004-4",
    "valor_fipe": "120000.00",
    "mes_referencia_fipe": "maio/2026",
    "snapshot_json": {"marca_id": "21", "modelo_id": "4591", "year_id": "2023-1"},
}


@pytest.mark.asyncio
async def test_create_and_list_vehicles(client, session):
    _, email = await _seed(session)
    tokens = (await client.post("/api/v1/auth/login", json={"email": email, "password": "pass123!"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post("/api/v1/vehicles", json=_VEHICLE_BODY, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "ativo"

    list_resp = await client.get("/api/v1/vehicles", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_set_vehicle_status(client, session):
    _, email = await _seed(session)
    tokens = (await client.post("/api/v1/auth/login", json={"email": email, "password": "pass123!"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    v = (await client.post("/api/v1/vehicles", json=_VEHICLE_BODY, headers=headers)).json()
    resp = await client.post(
        f"/api/v1/vehicles/{v['id']}/status",
        json={"status": "reservado"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reservado"


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_422(client, session):
    _, email = await _seed(session)
    tokens = (await client.post("/api/v1/auth/login", json={"email": email, "password": "pass123!"})).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    v = (await client.post("/api/v1/vehicles", json=_VEHICLE_BODY, headers=headers)).json()
    await client.post(f"/api/v1/vehicles/{v['id']}/status", json={"status": "vendido"}, headers=headers)
    resp = await client.post(
        f"/api/v1/vehicles/{v['id']}/status",
        json={"status": "ativo"},
        headers=headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 3: Run all tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_client_endpoints.py tests/test_vehicle_endpoints.py -v
```

Expected: all PASS

- [ ] **Step 4: Run full test suite**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/ -v --tb=short
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_client_endpoints.py backend/tests/test_vehicle_endpoints.py
git commit -m "test(endpoints): add client and vehicle endpoint integration tests"
```

---

## Self-review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| `clients` table with all fields | Task 2, 3 |
| `vehicles` table with all fields | Task 2, 3 |
| `fipe_cache` global table | Task 2, 3 |
| `client_service.create/get/list/update/deactivate` | Task 7 |
| mod-11 validation via `document_validation` | Task 7 |
| `vehicle_service.create/update/set_status/list/refresh_fipe` | Task 8 |
| `fipe_service` wraps `build_fipe_chain` | Task 5 |
| `PostgresFipeCache` with TTL | Task 5 |
| `cep_service.lookup(cep)` fail-open | Task 6 |
| All API endpoints from spec | Task 9 |
| FIPE chain tests: primary-ok/fallback/cache-hit/both-fail | Task 10 |
| CPF/CNPJ mod-11 tests | Task 7 |
| Import path fix + sync exclusion | Task 1 |
| Migration 004 | Task 2 |
| Simulation FK links (nullable DB, required API) | Tasks 3, 4, 9 |
| Tenant isolation (cross-tenant 404/403) | Tasks 7, 8, 11 |
| FIPE cache hits logged via loguru | Tasks 5 (logger.debug in fipe_cache.py) |
| `snapshot_json` contains `marca_id`, `modelo_id`, `year_id` for refresh | Task 8 (documents in VehicleIn) |
