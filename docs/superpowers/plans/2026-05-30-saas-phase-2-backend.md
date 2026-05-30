# Phase 2 — Simulação Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the desktop financial simulation pipeline (Price + IOF + extras + CET) behind tenant-scoped REST endpoints.

**Architecture:** New tables via a single Alembic migration; pure-Python computation via `finacialsim_core`; thin service layer orchestrates DB reads/writes; FastAPI routers follow the same pattern as Phase 1 (`api/users.py`).

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, `finacialsim_core` (vendored)

---

## File Map

**Create:**

- `backend/alembic/versions/003_simulation_tables.py`
- `backend/finacialsim_saas/schemas/__init__.py`
- `backend/finacialsim_saas/schemas/types.py`
- `backend/finacialsim_saas/schemas/business_rules.py`
- `backend/finacialsim_saas/schemas/simulations.py`
- `backend/finacialsim_saas/services/__init__.py`
- `backend/finacialsim_saas/services/rules_service.py`
- `backend/finacialsim_saas/services/simulation_service.py`
- `backend/finacialsim_saas/api/business_rules.py`
- `backend/finacialsim_saas/api/simulations.py`
- `backend/tests/test_business_rules_endpoint.py`
- `backend/tests/test_simulation_service.py`
- `backend/tests/test_simulation_endpoints.py`

**Modify:**

- `backend/finacialsim_saas/data/models.py` — add 7 new ORM models
- `backend/finacialsim_saas/cli/main.py` — seed `business_rules` on tenant create
- `backend/finacialsim_saas/main.py` — include new routers

---

## Task 1: Alembic migration — all Phase 2 tables

**Files:**

- Create: `backend/alembic/versions/003_simulation_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""simulation tables — business_rules, simulation_counters, simulations, fees, extras, rows, extraordinary

Revision ID: 003
Revises: 002
Create Date: 2026-05-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE simulation_status AS ENUM ('rascunho', 'confirmado', 'arquivado')"
    )

    op.create_table(
        "business_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("chave", sa.Text, nullable=False),
        sa.Column("valor_json", JSONB, nullable=False),
        sa.Column("descricao", sa.Text, nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_por", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_business_rules_tenant", "business_rules", ["tenant_id"])
    op.create_unique_constraint(
        "uq_business_rules_tenant_chave", "business_rules", ["tenant_id", "chave"]
    )

    op.create_table(
        "simulation_counters",
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("next_val", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("tenant_id", "year"),
    )

    op.create_table(
        "simulations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("codigo", sa.Text, nullable=False),
        sa.Column("cliente_nome", sa.Text, nullable=True),
        sa.Column("veiculo_descricao", sa.Text, nullable=True),
        sa.Column("valor_veiculo", NUMERIC(18, 2), nullable=False),
        sa.Column("valor_entrada", NUMERIC(18, 2), nullable=False),
        sa.Column("valor_financiado", NUMERIC(18, 2), nullable=False),
        sa.Column("taxa_mensal", NUMERIC(10, 6), nullable=False),
        sa.Column("prazo_meses", sa.Integer, nullable=False),
        sa.Column("data_liberacao", sa.Date, nullable=False),
        sa.Column("primeiro_vencimento", sa.Date, nullable=False),
        sa.Column("incluir_iof", sa.Boolean, nullable=False),
        sa.Column("iof_total", NUMERIC(18, 2), nullable=False),
        sa.Column("parcela_financiamento", NUMERIC(18, 2), nullable=False),
        sa.Column("total_pago", NUMERIC(18, 2), nullable=False),
        sa.Column("total_juros", NUMERIC(18, 2), nullable=False),
        sa.Column("cet_mensal", NUMERIC(10, 6), nullable=False),
        sa.Column("cet_anual", NUMERIC(10, 6), nullable=False),
        sa.Column("status", sa.Enum(name="simulation_status", create_type=False),
                  nullable=False, server_default="confirmado"),
        sa.Column("rules_snapshot_json", JSONB, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=True, unique=True),
        sa.Column("criado_por", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_simulations_tenant", "simulations", ["tenant_id"])
    op.create_index("ix_simulations_tenant_criado_em",
                    "simulations", ["tenant_id", "criado_em"])
    op.create_unique_constraint(
        "uq_simulations_tenant_codigo", "simulations", ["tenant_id", "codigo"]
    )

    op.create_table(
        "simulation_fees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("valor", NUMERIC(18, 2), nullable=False),
        sa.Column("incluir_no_principal", sa.Boolean, nullable=False),
    )
    op.create_index("ix_simulation_fees_sim", "simulation_fees", ["simulation_id"])

    op.create_table(
        "simulation_extras",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("valor_total", NUMERIC(18, 2), nullable=False),
        sa.Column("modalidade", sa.Text, nullable=False),
        sa.Column("duracao_meses", sa.Integer, nullable=False),
        sa.Column("valor_por_parcela", NUMERIC(18, 2), nullable=False),
        sa.Column("ordem", sa.Integer, nullable=False),
    )
    op.create_index("ix_simulation_extras_sim", "simulation_extras", ["simulation_id"])

    op.create_table(
        "amortization_rows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("numero_parcela", sa.Integer, nullable=False),
        sa.Column("data_vencimento", sa.Date, nullable=False),
        sa.Column("dias_periodo", sa.Integer, nullable=False),
        sa.Column("saldo_anterior", NUMERIC(18, 2), nullable=False),
        sa.Column("juros", NUMERIC(18, 2), nullable=False),
        sa.Column("amortizacao", NUMERIC(18, 2), nullable=False),
        sa.Column("parcela", NUMERIC(18, 2), nullable=False),
        sa.Column("saldo_devedor", NUMERIC(18, 2), nullable=False),
        sa.Column("extras_total", NUMERIC(18, 2), nullable=False),
        sa.Column("parcela_total", NUMERIC(18, 2), nullable=False),
        sa.Column("ajuste_arredondamento", NUMERIC(18, 2), nullable=False),
    )
    op.create_index("ix_amortization_rows_sim_parcela",
                    "amortization_rows", ["simulation_id", "numero_parcela"])

    op.create_table(
        "extraordinary_amortizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("simulation_id", UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("valor", NUMERIC(18, 2), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_extraordinary_sim", "extraordinary_amortizations", ["simulation_id"])


def downgrade() -> None:
    op.drop_table("extraordinary_amortizations")
    op.drop_table("amortization_rows")
    op.drop_table("simulation_extras")
    op.drop_table("simulation_fees")
    op.drop_table("simulations")
    op.drop_table("simulation_counters")
    op.drop_table("business_rules")
    op.execute("DROP TYPE simulation_status")
```

- [ ] **Step 2: Run migration against dev DB**

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/financialsim" \
  uv run alembic upgrade head
```

Expected: `Running upgrade 002 -> 003` with no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/003_simulation_tables.py
git commit -m "feat(db): add Phase 2 simulation tables migration"
```

---

## Task 2: ORM models

**Files:**

- Modify: `backend/finacialsim_saas/data/models.py`

- [ ] **Step 1: Write failing import test**

Add to `backend/tests/test_models.py` (already exists):

```python
def test_all_phase2_models_importable_and_tables_exist(engine):
    from finacialsim_saas.data.models import (
        BusinessRule, SimulationCounter, Simulation,
        SimulationFee, SimulationExtra, AmortizationRow,
        ExtraordinaryAmortization, SimulationStatus,
    )
    from sqlalchemy import inspect, text
    import asyncio
    async def _check():
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda c: inspect(c).get_table_names()
            )
        return tables
    tables = asyncio.run(_check())
    for t in ("business_rules", "simulation_counters", "simulations",
              "simulation_fees", "simulation_extras", "amortization_rows",
              "extraordinary_amortizations"):
        assert t in tables
```

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 2: Add models to `backend/finacialsim_saas/data/models.py`**

Append after the existing `NotificationsOutbox` class:

```python
import enum as _enum
from decimal import Decimal


class SimulationStatus(_enum.Enum):
    rascunho = "rascunho"
    confirmado = "confirmado"
    arquivado = "arquivado"


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    chave: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valor_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    descricao: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    atualizado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "chave", name="uq_business_rules_tenant_chave"),
    )


class SimulationCounter(Base):
    __tablename__ = "simulation_counters"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    next_val: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )

    __table_args__ = (sa.PrimaryKeyConstraint("tenant_id", "year"),)


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    codigo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cliente_nome: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    veiculo_descricao: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    valor_veiculo: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    valor_entrada: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    valor_financiado: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    taxa_mensal: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    prazo_meses: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    data_liberacao: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    primeiro_vencimento: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    incluir_iof: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    iof_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    parcela_financiamento: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    total_pago: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    total_juros: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    cet_mensal: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    cet_anual: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    status: Mapped[SimulationStatus] = mapped_column(
        sa.Enum(SimulationStatus, name="simulation_status", native_enum=True),
        nullable=False, server_default="confirmado"
    )
    rules_snapshot_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True, unique=True)
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
        sa.Index("ix_simulations_tenant_criado_em", "tenant_id", "criado_em"),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_simulations_tenant_codigo"),
    )


class SimulationFee(Base):
    __tablename__ = "simulation_fees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    nome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valor: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    incluir_no_principal: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)


class SimulationExtra(Base):
    __tablename__ = "simulation_extras"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tipo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    nome: Mapped[str] = mapped_column(sa.Text, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    modalidade: Mapped[str] = mapped_column(sa.Text, nullable=False)
    duracao_meses: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    valor_por_parcela: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    ordem: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class AmortizationRow(Base):
    __tablename__ = "amortization_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    numero_parcela: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    data_vencimento: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    dias_periodo: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    saldo_anterior: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    juros: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    amortizacao: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    parcela: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    saldo_devedor: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    extras_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    parcela_total: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    ajuste_arredondamento: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)

    __table_args__ = (
        sa.Index("ix_amortization_rows_sim_parcela", "simulation_id", "numero_parcela"),
    )


class ExtraordinaryAmortization(Base):
    __tablename__ = "extraordinary_amortizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    data: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
```

- [ ] **Step 3: Run test**

```bash
cd backend && uv run pytest tests/test_models.py -v
```

Expected: both `test_all_phase1_models_importable_and_tables_exist` and `test_all_phase2_models_importable_and_tables_exist` PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/data/models.py backend/tests/test_models.py
git commit -m "feat(models): add Phase 2 simulation ORM models"
```

---

## Task 3: Seed `business_rules` on tenant creation

**Files:**

- Modify: `backend/finacialsim_saas/cli/main.py`

The seed covers all 14 rule keys from the spec. Default values match the desktop's `DEFAULT_RULES` plus IOF defaults from `finacialsim_core`.

- [ ] **Step 1: Add `seed_business_rules` function in `cli/main.py`**

Add this function after the imports:

```python
from datetime import date as _date

_DEFAULT_BUSINESS_RULES: list[tuple[str, object, str]] = [
    ("entrada_minima_pct", "0.10", "Percentual mínimo de entrada"),
    ("prazo_minimo_meses", 12, "Prazo mínimo em meses"),
    ("prazo_maximo_meses", 72, "Prazo máximo em meses"),
    ("taxa_minima_mes", "0.005", "Taxa mensal mínima"),
    ("taxa_maxima_mes", "0.05", "Taxa mensal máxima"),
    ("dias_max_carencia", 90, "Dias máximos de carência"),
    ("valor_minimo_financiado", "5000.00", "Valor mínimo financiado"),
    ("iof_fixo_pct", "0.0038", "IOF fixo percentual"),
    ("iof_diario_pct", "0.000082", "IOF diário percentual"),
    ("iof_diario_max_dias", 365, "IOF diário — máximo de dias"),
    ("incluir_iof_default", True, "Incluir IOF por padrão"),
    ("rateio_ipva_meses_default", 12, "Meses de rateio IPVA padrão"),
    ("rateio_emplacamento_meses_default", 3, "Meses de rateio emplacamento padrão"),
    ("taxa_por_prazo_curva", [
        {"ate_meses": 24, "taxa_mensal": "0.0159"},
        {"ate_meses": 36, "taxa_mensal": "0.0179"},
        {"ate_meses": 48, "taxa_mensal": "0.0199"},
        {"ate_meses": 60, "taxa_mensal": "0.0219"},
        {"ate_meses": 72, "taxa_mensal": "0.0239"},
    ], "Curva de taxa sugerida por prazo"),
]


async def _seed_business_rules(session, tenant_id: "uuid.UUID") -> None:
    from finacialsim_saas.data.models import BusinessRule
    for chave, valor, descricao in _DEFAULT_BUSINESS_RULES:
        rule = BusinessRule(
            tenant_id=tenant_id,
            chave=chave,
            valor_json=valor,
            descricao=descricao,
        )
        session.add(rule)
```

- [ ] **Step 2: Call `_seed_business_rules` inside `tenant_create`**

In `tenant_create._create()`, after `await session.flush()` and before `await session.commit()`:

```python
            await _seed_business_rules(session, tenant.id)
```

Full updated `_create` body:

```python
    async def _create():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
            if existing.scalar_one_or_none() is not None:
                typer.echo(f"Error: tenant slug '{slug}' already exists.", err=True)
                raise typer.Exit(1)
            tenant = Tenant(name=name, slug=slug)
            session.add(tenant)
            await session.flush()
            svc = AuthService(session, settings)
            await svc.register_user(
                tenant_id=tenant.id,
                email=admin_email,
                password=admin_password,
                name=admin_email,
                role=Role.admin,
            )
            await _seed_business_rules(session, tenant.id)
            await session.commit()
            typer.echo(f"Tenant '{name}' (slug={slug}) created. Admin: {admin_email}")
        await engine.dispose()
```

- [ ] **Step 3: Run CLI test**

```bash
cd backend && uv run pytest tests/test_cli.py -v
```

Expected: PASS (test creates tenant and checks basic output — existing test still passes).

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/cli/main.py
git commit -m "feat(cli): seed business_rules on tenant create"
```

---

## Task 4: Schemas — `DecimalStr` type and base schemas

**Files:**

- Create: `backend/finacialsim_saas/schemas/__init__.py`
- Create: `backend/finacialsim_saas/schemas/types.py`
- Create: `backend/finacialsim_saas/schemas/business_rules.py`

- [ ] **Step 1: Write failing test for DecimalStr**

Create `backend/tests/test_schemas.py`:

```python
import json
from decimal import Decimal
from finacialsim_saas.schemas.types import DecimalStr
from pydantic import BaseModel


def test_decimal_str_serializes_as_string():
    class M(BaseModel):
        v: DecimalStr

    m = M(v=Decimal("1234.56"))
    data = json.loads(m.model_dump_json())
    assert data["v"] == "1234.56"
    assert isinstance(data["v"], str)


def test_decimal_str_parses_from_string():
    class M(BaseModel):
        v: DecimalStr

    m = M(v="99.99")
    assert m.v == Decimal("99.99")
    assert isinstance(m.v, Decimal)


def test_business_rules_out_has_all_14_keys():
    from finacialsim_saas.schemas.business_rules import BusinessRulesOut
    fields = set(BusinessRulesOut.model_fields.keys())
    required = {
        "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
        "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
        "valor_minimo_financiado", "iof_fixo_pct", "iof_diario_pct",
        "iof_diario_max_dias", "incluir_iof_default",
        "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
        "taxa_por_prazo_curva",
    }
    assert required.issubset(fields)
```

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create `schemas/__init__.py`**

```python
```

(empty)

- [ ] **Step 3: Create `schemas/types.py`**

```python
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

DecimalStr = Annotated[
    Decimal,
    BeforeValidator(lambda v: Decimal(str(v)) if not isinstance(v, Decimal) else v),
    PlainSerializer(lambda v: str(v), return_type=str),
]
```

- [ ] **Step 4: Create `schemas/business_rules.py`**

```python
from __future__ import annotations

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class RateCurvePointOut(BaseModel):
    ate_meses: int
    taxa_mensal: DecimalStr


class BusinessRulesOut(BaseModel):
    entrada_minima_pct: DecimalStr
    prazo_minimo_meses: int
    prazo_maximo_meses: int
    taxa_minima_mes: DecimalStr
    taxa_maxima_mes: DecimalStr
    dias_max_carencia: int
    valor_minimo_financiado: DecimalStr
    iof_fixo_pct: DecimalStr
    iof_diario_pct: DecimalStr
    iof_diario_max_dias: int
    incluir_iof_default: bool
    rateio_ipva_meses_default: int
    rateio_emplacamento_meses_default: int
    taxa_por_prazo_curva: list[RateCurvePointOut]
```

- [ ] **Step 5: Run tests**

```bash
cd backend && uv run pytest tests/test_schemas.py -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/schemas/ backend/tests/test_schemas.py
git commit -m "feat(schemas): add DecimalStr type and BusinessRulesOut schema"
```

---

## Task 5: Simulation schemas

**Files:**

- Create: `backend/finacialsim_saas/schemas/simulations.py`

- [ ] **Step 1: Add schema tests to `test_schemas.py`**

Append to `backend/tests/test_schemas.py`:

```python
def test_simulation_create_validates_required_fields():
    from finacialsim_saas.schemas.simulations import SimulationCreate
    import pytest
    with pytest.raises(Exception):
        SimulationCreate()  # missing required fields


def test_fee_in_schema():
    from finacialsim_saas.schemas.simulations import FeeIn
    fee = FeeIn(nome="Tarifa cadastro", valor="150.00", incluir_no_principal=True)
    assert fee.valor == __import__("decimal").Decimal("150.00")


def test_extra_in_schema():
    from finacialsim_saas.schemas.simulations import ExtraIn
    extra = ExtraIn(
        tipo="protecao", nome="Proteção Veicular", valor_total="100.00",
        modalidade="mensal_continuo", duracao_meses=24, ordem=1,
    )
    assert extra.modalidade == "mensal_continuo"
```

Run: `cd backend && uv run pytest tests/test_schemas.py::test_fee_in_schema -v`
Expected: FAIL

- [ ] **Step 2: Create `schemas/simulations.py`**

```python
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class FeeIn(BaseModel):
    nome: str
    valor: DecimalStr
    incluir_no_principal: bool


class ExtraIn(BaseModel):
    tipo: str
    nome: str
    valor_total: DecimalStr
    modalidade: str  # mensal_continuo | rateio_meses | unico_inicial
    duracao_meses: int
    ordem: int


class SimulationCreate(BaseModel):
    cliente_nome: str | None = None
    veiculo_descricao: str | None = None
    valor_veiculo: DecimalStr
    valor_entrada: DecimalStr
    taxa_mensal: DecimalStr
    prazo_meses: int
    data_liberacao: date
    primeiro_vencimento: date
    incluir_iof: bool = True
    fees: list[FeeIn] = []
    extras: list[ExtraIn] = []
    idempotency_key: str | None = None


class SimulationPreviewRequest(BaseModel):
    valor_veiculo: DecimalStr
    valor_entrada: DecimalStr
    taxa_mensal: DecimalStr
    prazo_meses: int
    data_liberacao: date
    primeiro_vencimento: date
    incluir_iof: bool = True
    fees: list[FeeIn] = []
    extras: list[ExtraIn] = []


class FeeOut(BaseModel):
    id: uuid.UUID
    nome: str
    valor: DecimalStr
    incluir_no_principal: bool


class ExtraOut(BaseModel):
    id: uuid.UUID
    tipo: str
    nome: str
    valor_total: DecimalStr
    modalidade: str
    duracao_meses: int
    valor_por_parcela: DecimalStr
    ordem: int


class AmortizationRowOut(BaseModel):
    numero_parcela: int
    data_vencimento: date
    dias_periodo: int
    saldo_anterior: DecimalStr
    juros: DecimalStr
    amortizacao: DecimalStr
    parcela: DecimalStr
    saldo_devedor: DecimalStr
    extras_total: DecimalStr
    parcela_total: DecimalStr
    ajuste_arredondamento: DecimalStr


class SimulationSummary(BaseModel):
    parcela_financiamento: DecimalStr
    parcela_total_primeiro_ano: DecimalStr
    parcela_total_apos_rateio: DecimalStr
    valor_financiado: DecimalStr
    total_pago: DecimalStr
    total_juros: DecimalStr
    pct_juros: DecimalStr
    cet_mensal: DecimalStr
    cet_anual: DecimalStr
    total_pago_pelo_cliente: DecimalStr
    iof_total: DecimalStr


class SimulationPreviewResponse(BaseModel):
    summary: SimulationSummary
    rows: list[AmortizationRowOut]


class SimulationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    codigo: str
    cliente_nome: str | None
    veiculo_descricao: str | None
    valor_veiculo: DecimalStr
    valor_entrada: DecimalStr
    valor_financiado: DecimalStr
    taxa_mensal: DecimalStr
    prazo_meses: int
    data_liberacao: date
    primeiro_vencimento: date
    incluir_iof: bool
    iof_total: DecimalStr
    parcela_financiamento: DecimalStr
    total_pago: DecimalStr
    total_juros: DecimalStr
    cet_mensal: DecimalStr
    cet_anual: DecimalStr
    status: str
    criado_por: uuid.UUID
    criado_em: datetime
    atualizado_em: datetime
    fees: list[FeeOut] = []
    extras: list[ExtraOut] = []
    rows: list[AmortizationRowOut] = []
    summary: SimulationSummary | None = None


class SimulationListItem(BaseModel):
    id: uuid.UUID
    codigo: str
    cliente_nome: str | None
    veiculo_descricao: str | None
    valor_veiculo: DecimalStr
    valor_financiado: DecimalStr
    prazo_meses: int
    taxa_mensal: DecimalStr
    status: str
    criado_em: datetime


class SimulationListPage(BaseModel):
    items: list[SimulationListItem]
    next_cursor: str | None


class ValidationIssueOut(BaseModel):
    field: str
    message: str
    level: str
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_schemas.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/schemas/simulations.py backend/tests/test_schemas.py
git commit -m "feat(schemas): add simulation request/response schemas"
```

---

## Task 6: `rules_service.py`

**Files:**

- Create: `backend/finacialsim_saas/services/__init__.py`
- Create: `backend/finacialsim_saas/services/rules_service.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_simulation_service.py`:

```python
import asyncio
import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import uuid4
from datetime import date

from finacialsim_saas.data.models import BusinessRule, Tenant, User, Role


@pytest_asyncio.fixture
async def tenant(session):
    t = Tenant(name="Test Co", slug=f"test-{uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    return t


@pytest_asyncio.fixture
async def user(session, tenant):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    svc = AuthService(session, get_settings())
    u = await svc.register_user(
        tenant_id=tenant.id, email=f"u-{uuid4().hex[:6]}@test.com",
        password="password123", name="Test User", role=Role.user,
    )
    await session.flush()
    return u


@pytest_asyncio.fixture
async def rules_seeded(session, tenant):
    from finacialsim_saas.cli.main import _seed_business_rules
    await _seed_business_rules(session, tenant.id)
    await session.flush()


@pytest.mark.asyncio
async def test_get_rules_returns_all_14_keys(session, tenant, rules_seeded):
    from finacialsim_saas.services.rules_service import RulesService
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert "entrada_minima_pct" in rules
    assert "taxa_por_prazo_curva" in rules
    assert len(rules) == 14


@pytest.mark.asyncio
async def test_get_rules_raises_on_missing_rule(session, tenant):
    from finacialsim_saas.services.rules_service import RulesService
    from finacialsim_saas.errors import AppError
    svc = RulesService(session)
    with pytest.raises(AppError, match="business rule"):
        await svc.get_rules(tenant.id)
```

Run: `cd backend && uv run pytest tests/test_simulation_service.py::test_get_rules_returns_all_14_keys -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create `services/__init__.py`**

```python
```

(empty)

- [ ] **Step 3: Create `services/rules_service.py`**

```python
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import BusinessRule
from finacialsim_saas.errors import AppError

_REQUIRED_RULES = frozenset([
    "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
    "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
    "valor_minimo_financiado", "iof_fixo_pct", "iof_diario_pct",
    "iof_diario_max_dias", "incluir_iof_default",
    "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
    "taxa_por_prazo_curva",
])


class RulesService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_rules(self, tenant_id: uuid.UUID) -> dict:
        result = await self._s.execute(
            select(BusinessRule).where(BusinessRule.tenant_id == tenant_id)
        )
        rows = result.scalars().all()
        rules = {r.chave: r.valor_json for r in rows}
        missing = _REQUIRED_RULES - rules.keys()
        if missing:
            raise AppError(
                f"business rule(s) not configured for tenant: {sorted(missing)}"
            )
        return rules

    async def snapshot(self, tenant_id: uuid.UUID) -> dict:
        return await self.get_rules(tenant_id)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_simulation_service.py::test_get_rules_returns_all_14_keys tests/test_simulation_service.py::test_get_rules_raises_on_missing_rule -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/finacialsim_saas/services/ backend/tests/test_simulation_service.py
git commit -m "feat(services): add RulesService with get_rules and snapshot"
```

---

## Task 7: `simulation_service.py` — computation helpers

**Files:**

- Create: `backend/finacialsim_saas/services/simulation_service.py`

- [ ] **Step 1: Add computation tests to `test_simulation_service.py`**

Append:

```python
def _make_preview_payload():
    from finacialsim_saas.schemas.simulations import SimulationPreviewRequest
    return SimulationPreviewRequest(
        valor_veiculo="50000.00",
        valor_entrada="10000.00",
        taxa_mensal="0.0199",
        prazo_meses=24,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )


@pytest.mark.asyncio
async def test_preview_returns_schedule_rows(session, tenant, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid4(), tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    result = await svc.preview(_make_preview_payload(), ctx)
    assert len(result.rows) == 24
    assert result.summary.valor_financiado == Decimal("40000.00")


@pytest.mark.asyncio
async def test_preview_no_iof_iof_total_is_zero(session, tenant, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid4(), tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    result = await svc.preview(_make_preview_payload(), ctx)
    assert result.summary.iof_total == Decimal("0.00")


@pytest.mark.asyncio
async def test_preview_total_pago_pelo_cliente_includes_entrada(session, tenant, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid4(), tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    result = await svc.preview(_make_preview_payload(), ctx)
    expected = result.summary.total_pago + Decimal("10000.00")
    assert result.summary.total_pago_pelo_cliente == expected
```

Run: `cd backend && uv run pytest tests/test_simulation_service.py::test_preview_returns_schedule_rows -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create `services/simulation_service.py`** (computation helpers + preview)

```python
from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_core.cet import compute_cet
from finacialsim_core.extras import Extra, ExtraModalidade, compute_extras_per_parcela
from finacialsim_core.iof import IofConfig, compute_financed_amount_with_iof
from finacialsim_core.money import quantize_brl
from finacialsim_core.price_table import build_schedule
from finacialsim_core.validators import SimulationInput, ValidationRules, validate_simulation

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import (
    AmortizationRow, Simulation, SimulationExtra, SimulationFee,
    SimulationStatus,
)
from finacialsim_saas.errors import AppError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.simulations import (
    AmortizationRowOut, ExtraIn, FeeIn, SimulationCreate, SimulationListItem,
    SimulationListPage, SimulationOut, SimulationPreviewRequest,
    SimulationPreviewResponse, SimulationSummary, ValidationIssueOut,
    FeeOut, ExtraOut,
)
from finacialsim_saas.services.rules_service import RulesService


def _iof_config_from_rules(rules: dict) -> IofConfig:
    return IofConfig(
        fixo_pct=Decimal(str(rules["iof_fixo_pct"])),
        diario_pct=Decimal(str(rules["iof_diario_pct"])),
        max_dias=int(rules["iof_diario_max_dias"]),
    )


def _validation_rules_from_rules(rules: dict) -> ValidationRules:
    return ValidationRules(
        entrada_minima_pct=Decimal(str(rules["entrada_minima_pct"])),
        prazo_minimo_meses=int(rules["prazo_minimo_meses"]),
        prazo_maximo_meses=int(rules["prazo_maximo_meses"]),
        taxa_minima_mes=Decimal(str(rules["taxa_minima_mes"])),
        taxa_maxima_mes=Decimal(str(rules["taxa_maxima_mes"])),
        dias_max_carencia=int(rules["dias_max_carencia"]),
        valor_minimo_financiado=Decimal(str(rules["valor_minimo_financiado"])),
    )


def _extras_from_input(extras_in: list[ExtraIn]) -> list[Extra]:
    return [
        Extra(
            tipo=e.tipo,
            nome=e.nome,
            valor_total=e.valor_total,
            modalidade=ExtraModalidade(e.modalidade),
            duracao_meses=e.duracao_meses,
            ordem=e.ordem,
        )
        for e in extras_in
    ]


@dataclass
class _ComputeResult:
    valor_financiado: Decimal
    iof_total: Decimal
    schedule_rows: list  # list[ScheduleRow]
    extras_per_parcela: list[Decimal]
    summary: SimulationSummary


def _compute(
    valor_veiculo: Decimal,
    valor_entrada: Decimal,
    taxa_mensal: Decimal,
    prazo_meses: int,
    data_liberacao: date,
    primeiro_vencimento: date,
    incluir_iof: bool,
    fees_in: list[FeeIn],
    extras_in: list[ExtraIn],
    rules: dict,
) -> _ComputeResult:
    d1 = (primeiro_vencimento - data_liberacao).days
    base_pv = valor_veiculo - valor_entrada
    base_pv += sum(
        (Decimal(str(f.valor)) for f in fees_in if f.incluir_no_principal),
        Decimal("0.00"),
    )

    iof_config = _iof_config_from_rules(rules)
    financed = compute_financed_amount_with_iof(
        pv_inicial=base_pv,
        taxa_mensal=taxa_mensal,
        n=prazo_meses,
        d1=d1,
        data_liberacao=data_liberacao,
        config=iof_config,
        incluir_iof=incluir_iof,
    )
    final_pv = financed.valor_financiado
    iof_total = financed.iof.total
    schedule = financed.schedule

    extras = _extras_from_input(extras_in)
    extras_per_parcela = compute_extras_per_parcela(extras, prazo_meses)

    total_pago = sum(
        (row.parcela + extras_per_parcela[i] for i, row in enumerate(schedule.rows)),
        Decimal("0.00"),
    )
    total_pago = quantize_brl(total_pago)

    # parcela_total_apos_rateio: base PMT once all extras have expired
    parcela_total_apos_rateio = schedule.pmt

    cet = compute_cet(
        valor_liberado=valor_veiculo - valor_entrada,
        schedule=schedule,
        d1=d1,
    )

    summary = SimulationSummary(
        parcela_financiamento=schedule.pmt,
        parcela_total_primeiro_ano=quantize_brl(schedule.rows[0].parcela + extras_per_parcela[0]),
        parcela_total_apos_rateio=parcela_total_apos_rateio,
        valor_financiado=final_pv,
        total_pago=total_pago,
        total_juros=schedule.total_juros,
        pct_juros=quantize_brl(schedule.total_juros / final_pv * Decimal("100")),
        cet_mensal=cet.cet_mes,
        cet_anual=cet.cet_ano,
        total_pago_pelo_cliente=quantize_brl(total_pago + valor_entrada),
        iof_total=iof_total,
    )

    return _ComputeResult(
        valor_financiado=final_pv,
        iof_total=iof_total,
        schedule_rows=list(schedule.rows),
        extras_per_parcela=extras_per_parcela,
        summary=summary,
    )


def _rows_to_out(result: _ComputeResult) -> list[AmortizationRowOut]:
    out = []
    for i, row in enumerate(result.schedule_rows):
        extras_total = result.extras_per_parcela[i]
        out.append(AmortizationRowOut(
            numero_parcela=row.numero_parcela,
            data_vencimento=row.data_vencimento,
            dias_periodo=row.dias_periodo,
            saldo_anterior=row.saldo_anterior,
            juros=row.juros,
            amortizacao=row.amortizacao,
            parcela=row.parcela,
            saldo_devedor=row.saldo_devedor,
            extras_total=extras_total,
            parcela_total=quantize_brl(row.parcela + extras_total),
            ajuste_arredondamento=row.ajuste_arredondamento,
        ))
    return out


class SimulationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._rules_svc = RulesService(session)

    async def preview(
        self, payload: SimulationPreviewRequest, ctx: RequestContext
    ) -> SimulationPreviewResponse:
        rules = await self._rules_svc.get_rules(ctx.tenant_id)
        result = _compute(
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            fees_in=payload.fees,
            extras_in=payload.extras,
            rules=rules,
        )
        return SimulationPreviewResponse(
            summary=result.summary,
            rows=_rows_to_out(result),
        )
```

- [ ] **Step 3: Run preview tests**

```bash
cd backend && uv run pytest tests/test_simulation_service.py -k "preview" -v
```

Expected: all 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/services/simulation_service.py backend/tests/test_simulation_service.py
git commit -m "feat(services): add SimulationService.preview with core computation"
```

---

## Task 8: `simulation_service.py` — create, get, list, update, archive, clone

**Files:**

- Modify: `backend/finacialsim_saas/services/simulation_service.py`

- [ ] **Step 1: Add create/get/CRUD tests to `test_simulation_service.py`**

Append:

```python
@pytest.mark.asyncio
async def test_create_persists_simulation_and_rows(session, tenant, user, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role, SimulationStatus
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        valor_veiculo="50000.00",
        valor_entrada="10000.00",
        taxa_mensal="0.0199",
        prazo_meses=24,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    sim = await svc.create(payload, ctx)
    await session.commit()

    fetched = await svc.get(sim.id, ctx)
    assert fetched.id == sim.id
    assert len(fetched.rows) == 24
    assert fetched.status == "confirmado"
    assert fetched.codigo.startswith("SIM-")


@pytest.mark.asyncio
async def test_preview_and_create_agree_on_valor_financiado(session, tenant, user, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)

    preview_req = _make_preview_payload()
    preview = await svc.preview(preview_req, ctx)

    create_req = SimulationCreate(
        valor_veiculo=preview_req.valor_veiculo,
        valor_entrada=preview_req.valor_entrada,
        taxa_mensal=preview_req.taxa_mensal,
        prazo_meses=preview_req.prazo_meses,
        data_liberacao=preview_req.data_liberacao,
        primeiro_vencimento=preview_req.primeiro_vencimento,
        incluir_iof=preview_req.incluir_iof,
    )
    sim = await svc.create(create_req, ctx)
    await session.commit()
    fetched = await svc.get(sim.id, ctx)

    assert preview.summary.valor_financiado == fetched.valor_financiado
    assert len(preview.rows) == len(fetched.rows)
    for pr, fr in zip(preview.rows, fetched.rows):
        assert pr.parcela == fr.parcela
        assert pr.saldo_devedor == fr.saldo_devedor


@pytest.mark.asyncio
async def test_create_idempotency_key_returns_same_id(session, tenant, user, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    key = f"idem-{uuid4().hex}"
    payload = SimulationCreate(
        valor_veiculo="50000.00", valor_entrada="10000.00",
        taxa_mensal="0.0199", prazo_meses=24,
        data_liberacao=date(2026, 6, 1), primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False, idempotency_key=key,
    )
    sim1 = await svc.create(payload, ctx)
    await session.commit()
    sim2 = await svc.create(payload, ctx)
    assert sim1.id == sim2.id


@pytest.mark.asyncio
async def test_create_validates_against_rules(session, tenant, user, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        valor_veiculo="50000.00",
        valor_entrada="1000.00",  # 2% — below 10% minimum
        taxa_mensal="0.0199",
        prazo_meses=24,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    with pytest.raises(ValidationError):
        await svc.create(payload, ctx)


@pytest.mark.asyncio
async def test_cross_tenant_get_raises_404(session, tenant, user, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        valor_veiculo="50000.00", valor_entrada="10000.00",
        taxa_mensal="0.0199", prazo_meses=24,
        data_liberacao=date(2026, 6, 1), primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    sim = await svc.create(payload, ctx)
    await session.commit()

    other_tenant = Tenant(name="Other", slug=f"other-{uuid4().hex[:6]}")
    session.add(other_tenant)
    await session.flush()
    other_ctx = RequestContext(
        user_id=uuid4(), tenant_id=other_tenant.id, role=Role.user, iat=0.0
    )
    with pytest.raises(NotFoundError):
        await svc.get(sim.id, other_ctx)


@pytest.mark.asyncio
async def test_clone_creates_rascunho(session, tenant, user, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        valor_veiculo="50000.00", valor_entrada="10000.00",
        taxa_mensal="0.0199", prazo_meses=24,
        data_liberacao=date(2026, 6, 1), primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    original = await svc.create(payload, ctx)
    await session.commit()
    cloned = await svc.clone(original.id, ctx)
    await session.commit()

    assert cloned.id != original.id
    assert cloned.status == "rascunho"
    assert cloned.codigo != original.codigo
    assert cloned.valor_veiculo == original.valor_veiculo
```

Run: `cd backend && uv run pytest tests/test_simulation_service.py::test_create_persists_simulation_and_rows -v`
Expected: FAIL with `AttributeError` (no `create` method yet)

- [ ] **Step 2: Add `_generate_codigo`, `create`, `get`, `list`, `update`, `archive`, `clone` to `simulation_service.py`**

Append to the `SimulationService` class (after `preview`):

```python
    async def _generate_codigo(self, tenant_id: uuid.UUID) -> str:
        year = datetime.now(timezone.utc).year
        row = await self._s.execute(
            text(
                "INSERT INTO simulation_counters (tenant_id, year, next_val) "
                "VALUES (:tid, :yr, 2) "
                "ON CONFLICT (tenant_id, year) DO UPDATE "
                "SET next_val = simulation_counters.next_val + 1 "
                "RETURNING next_val - 1"
            ),
            {"tid": str(tenant_id), "yr": year},
        )
        n = row.scalar_one()
        return f"SIM-{year}-{n:05d}"

    async def create(
        self, payload: SimulationCreate, ctx: RequestContext
    ) -> SimulationOut:
        # Idempotency check
        if payload.idempotency_key:
            existing = await self._s.execute(
                select(Simulation).where(
                    Simulation.idempotency_key == payload.idempotency_key,
                    Simulation.tenant_id == ctx.tenant_id,
                )
            )
            sim = existing.scalar_one_or_none()
            if sim is not None:
                return await self.get(sim.id, ctx)

        rules = await self._rules_svc.get_rules(ctx.tenant_id)

        # Validate
        v_rules = _validation_rules_from_rules(rules)
        d1 = (payload.primeiro_vencimento - payload.data_liberacao).days
        issues = validate_simulation(
            SimulationInput(
                valor_veiculo=payload.valor_veiculo,
                valor_entrada=payload.valor_entrada,
                prazo_meses=payload.prazo_meses,
                taxa_mensal=payload.taxa_mensal,
                dias_carencia=d1,
            ),
            v_rules,
        )
        errors = [i for i in issues if i.level == "error"]
        if errors:
            raise ValidationError(
                "Simulation validation failed",
                details=[{"field": i.field, "message": i.message, "level": i.level}
                         for i in errors],
            )

        result = _compute(
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            fees_in=payload.fees,
            extras_in=payload.extras,
            rules=rules,
        )

        codigo = await self._generate_codigo(ctx.tenant_id)
        sim = Simulation(
            tenant_id=ctx.tenant_id,
            codigo=codigo,
            cliente_nome=payload.cliente_nome,
            veiculo_descricao=payload.veiculo_descricao,
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            valor_financiado=result.valor_financiado,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            iof_total=result.iof_total,
            parcela_financiamento=result.summary.parcela_financiamento,
            total_pago=result.summary.total_pago,
            total_juros=result.summary.total_juros,
            cet_mensal=result.summary.cet_mensal,
            cet_anual=result.summary.cet_anual,
            status=SimulationStatus.confirmado,
            rules_snapshot_json=rules,
            idempotency_key=payload.idempotency_key,
            criado_por=ctx.user_id,
        )
        self._s.add(sim)
        await self._s.flush()

        for fee in payload.fees:
            self._s.add(SimulationFee(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                nome=fee.nome, valor=fee.valor,
                incluir_no_principal=fee.incluir_no_principal,
            ))

        for extra in payload.extras:
            from finacialsim_core.extras import _valor_por_parcela, Extra, ExtraModalidade
            core_extra = Extra(
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=ExtraModalidade(extra.modalidade),
                duracao_meses=extra.duracao_meses, ordem=extra.ordem,
            )
            vparcela = _valor_por_parcela(core_extra)
            self._s.add(SimulationExtra(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=extra.modalidade, duracao_meses=extra.duracao_meses,
                valor_por_parcela=vparcela, ordem=extra.ordem,
            ))

        for row_out in _rows_to_out(result):
            self._s.add(AmortizationRow(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                numero_parcela=row_out.numero_parcela,
                data_vencimento=row_out.data_vencimento,
                dias_periodo=row_out.dias_periodo,
                saldo_anterior=row_out.saldo_anterior,
                juros=row_out.juros,
                amortizacao=row_out.amortizacao,
                parcela=row_out.parcela,
                saldo_devedor=row_out.saldo_devedor,
                extras_total=row_out.extras_total,
                parcela_total=row_out.parcela_total,
                ajuste_arredondamento=row_out.ajuste_arredondamento,
            ))

        await self._s.flush()
        return await self.get(sim.id, ctx)

    async def get(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
        from sqlalchemy.orm import selectinload
        result = await self._s.execute(
            select(Simulation).where(
                Simulation.id == sim_id,
                Simulation.tenant_id == ctx.tenant_id,
            )
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            raise NotFoundError(f"Simulation {sim_id} not found")

        fees_r = await self._s.execute(
            select(SimulationFee).where(SimulationFee.simulation_id == sim_id)
        )
        extras_r = await self._s.execute(
            select(SimulationExtra).where(SimulationExtra.simulation_id == sim_id)
        )
        rows_r = await self._s.execute(
            select(AmortizationRow)
            .where(AmortizationRow.simulation_id == sim_id)
            .order_by(AmortizationRow.numero_parcela)
        )
        fees = fees_r.scalars().all()
        extras = extras_r.scalars().all()
        rows = rows_r.scalars().all()

        row_outs = [
            AmortizationRowOut(
                numero_parcela=r.numero_parcela,
                data_vencimento=r.data_vencimento,
                dias_periodo=r.dias_periodo,
                saldo_anterior=r.saldo_anterior,
                juros=r.juros,
                amortizacao=r.amortizacao,
                parcela=r.parcela,
                saldo_devedor=r.saldo_devedor,
                extras_total=r.extras_total,
                parcela_total=r.parcela_total,
                ajuste_arredondamento=r.ajuste_arredondamento,
            )
            for r in rows
        ]

        total_pago = sum((r.parcela_total for r in rows), Decimal("0.00"))
        summary = SimulationSummary(
            parcela_financiamento=sim.parcela_financiamento,
            parcela_total_primeiro_ano=row_outs[0].parcela_total if row_outs else Decimal("0"),
            parcela_total_apos_rateio=sim.parcela_financiamento,
            valor_financiado=sim.valor_financiado,
            total_pago=total_pago,
            total_juros=sim.total_juros,
            pct_juros=quantize_brl(sim.total_juros / sim.valor_financiado * Decimal("100")),
            cet_mensal=sim.cet_mensal,
            cet_anual=sim.cet_anual,
            total_pago_pelo_cliente=quantize_brl(total_pago + sim.valor_entrada),
            iof_total=sim.iof_total,
        )

        return SimulationOut(
            id=sim.id,
            tenant_id=sim.tenant_id,
            codigo=sim.codigo,
            cliente_nome=sim.cliente_nome,
            veiculo_descricao=sim.veiculo_descricao,
            valor_veiculo=sim.valor_veiculo,
            valor_entrada=sim.valor_entrada,
            valor_financiado=sim.valor_financiado,
            taxa_mensal=sim.taxa_mensal,
            prazo_meses=sim.prazo_meses,
            data_liberacao=sim.data_liberacao,
            primeiro_vencimento=sim.primeiro_vencimento,
            incluir_iof=sim.incluir_iof,
            iof_total=sim.iof_total,
            parcela_financiamento=sim.parcela_financiamento,
            total_pago=total_pago,
            total_juros=sim.total_juros,
            cet_mensal=sim.cet_mensal,
            cet_anual=sim.cet_anual,
            status=sim.status.value,
            criado_por=sim.criado_por,
            criado_em=sim.criado_em,
            atualizado_em=sim.atualizado_em,
            fees=[FeeOut(id=f.id, nome=f.nome, valor=f.valor,
                         incluir_no_principal=f.incluir_no_principal) for f in fees],
            extras=[ExtraOut(id=e.id, tipo=e.tipo, nome=e.nome, valor_total=e.valor_total,
                             modalidade=e.modalidade, duracao_meses=e.duracao_meses,
                             valor_por_parcela=e.valor_por_parcela, ordem=e.ordem) for e in extras],
            rows=row_outs,
            summary=summary,
        )

    async def list(
        self,
        ctx: RequestContext,
        status: str | None = None,
        cliente_nome: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> SimulationListPage:
        from sqlalchemy import and_
        from datetime import datetime, timezone

        q = select(Simulation).where(Simulation.tenant_id == ctx.tenant_id)
        if status:
            q = q.where(Simulation.status == SimulationStatus(status))
        if cliente_nome:
            q = q.where(Simulation.cliente_nome.ilike(f"%{cliente_nome}%"))
        if date_from:
            q = q.where(Simulation.criado_em >= datetime(
                date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc
            ))
        if date_to:
            q = q.where(Simulation.criado_em < datetime(
                date_to.year, date_to.month, date_to.day + 1, tzinfo=timezone.utc
            ))
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode()
                cur_ts, cur_id = decoded.rsplit(",", 1)
                q = q.where(
                    (Simulation.criado_em < cur_ts) |
                    ((Simulation.criado_em == cur_ts) & (Simulation.id < cur_id))
                )
            except Exception:
                pass  # invalid cursor — ignore, return from start

        q = q.order_by(Simulation.criado_em.desc(), Simulation.id.desc()).limit(limit + 1)
        result = await self._s.execute(q)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more:
            last = items[-1]
            raw = f"{last.criado_em.isoformat()},{last.id}"
            next_cursor = base64.b64encode(raw.encode()).decode()

        return SimulationListPage(
            items=[
                SimulationListItem(
                    id=s.id, codigo=s.codigo, cliente_nome=s.cliente_nome,
                    veiculo_descricao=s.veiculo_descricao, valor_veiculo=s.valor_veiculo,
                    valor_financiado=s.valor_financiado, prazo_meses=s.prazo_meses,
                    taxa_mensal=s.taxa_mensal, status=s.status.value, criado_em=s.criado_em,
                )
                for s in items
            ],
            next_cursor=next_cursor,
        )

    async def update(
        self, sim_id: uuid.UUID, payload: SimulationCreate, ctx: RequestContext
    ) -> SimulationOut:
        result = await self._s.execute(
            select(Simulation).where(
                Simulation.id == sim_id,
                Simulation.tenant_id == ctx.tenant_id,
            )
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            raise NotFoundError(f"Simulation {sim_id} not found")
        if sim.status != SimulationStatus.rascunho:
            raise AppError("Only rascunho simulations can be updated", details=None)
        if str(sim.criado_por) != str(ctx.user_id) and ctx.role.value not in ("manager", "admin"):
            raise TenantAccessError("Cannot update another user's simulation")

        # Delete child rows and recompute
        await self._s.execute(
            text("DELETE FROM simulation_fees WHERE simulation_id = :sid"),
            {"sid": str(sim_id)},
        )
        await self._s.execute(
            text("DELETE FROM simulation_extras WHERE simulation_id = :sid"),
            {"sid": str(sim_id)},
        )
        await self._s.execute(
            text("DELETE FROM amortization_rows WHERE simulation_id = :sid"),
            {"sid": str(sim_id)},
        )

        rules = await self._rules_svc.get_rules(ctx.tenant_id)
        v_rules = _validation_rules_from_rules(rules)
        d1 = (payload.primeiro_vencimento - payload.data_liberacao).days
        issues = validate_simulation(
            SimulationInput(
                valor_veiculo=payload.valor_veiculo,
                valor_entrada=payload.valor_entrada,
                prazo_meses=payload.prazo_meses,
                taxa_mensal=payload.taxa_mensal,
                dias_carencia=d1,
            ),
            v_rules,
        )
        errors = [i for i in issues if i.level == "error"]
        if errors:
            raise ValidationError(
                "Simulation validation failed",
                details=[{"field": i.field, "message": i.message, "level": i.level}
                         for i in errors],
            )

        result_c = _compute(
            valor_veiculo=payload.valor_veiculo,
            valor_entrada=payload.valor_entrada,
            taxa_mensal=payload.taxa_mensal,
            prazo_meses=payload.prazo_meses,
            data_liberacao=payload.data_liberacao,
            primeiro_vencimento=payload.primeiro_vencimento,
            incluir_iof=payload.incluir_iof,
            fees_in=payload.fees,
            extras_in=payload.extras,
            rules=rules,
        )

        sim.cliente_nome = payload.cliente_nome
        sim.veiculo_descricao = payload.veiculo_descricao
        sim.valor_veiculo = payload.valor_veiculo
        sim.valor_entrada = payload.valor_entrada
        sim.valor_financiado = result_c.valor_financiado
        sim.taxa_mensal = payload.taxa_mensal
        sim.prazo_meses = payload.prazo_meses
        sim.data_liberacao = payload.data_liberacao
        sim.primeiro_vencimento = payload.primeiro_vencimento
        sim.incluir_iof = payload.incluir_iof
        sim.iof_total = result_c.iof_total
        sim.parcela_financiamento = result_c.summary.parcela_financiamento
        sim.total_pago = result_c.summary.total_pago
        sim.total_juros = result_c.summary.total_juros
        sim.cet_mensal = result_c.summary.cet_mensal
        sim.cet_anual = result_c.summary.cet_anual
        sim.rules_snapshot_json = rules
        sim.atualizado_em = datetime.now(timezone.utc)

        for fee in payload.fees:
            self._s.add(SimulationFee(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                nome=fee.nome, valor=fee.valor,
                incluir_no_principal=fee.incluir_no_principal,
            ))
        for extra in payload.extras:
            from finacialsim_core.extras import _valor_por_parcela, Extra, ExtraModalidade
            core_extra = Extra(
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=ExtraModalidade(extra.modalidade),
                duracao_meses=extra.duracao_meses, ordem=extra.ordem,
            )
            self._s.add(SimulationExtra(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=extra.modalidade, duracao_meses=extra.duracao_meses,
                valor_por_parcela=_valor_por_parcela(core_extra), ordem=extra.ordem,
            ))
        for row_out in _rows_to_out(result_c):
            self._s.add(AmortizationRow(
                simulation_id=sim.id, tenant_id=ctx.tenant_id,
                numero_parcela=row_out.numero_parcela,
                data_vencimento=row_out.data_vencimento,
                dias_periodo=row_out.dias_periodo,
                saldo_anterior=row_out.saldo_anterior,
                juros=row_out.juros,
                amortizacao=row_out.amortizacao,
                parcela=row_out.parcela,
                saldo_devedor=row_out.saldo_devedor,
                extras_total=row_out.extras_total,
                parcela_total=row_out.parcela_total,
                ajuste_arredondamento=row_out.ajuste_arredondamento,
            ))

        await self._s.flush()
        return await self.get(sim.id, ctx)

    async def archive(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
        result = await self._s.execute(
            select(Simulation).where(
                Simulation.id == sim_id,
                Simulation.tenant_id == ctx.tenant_id,
            )
        )
        sim = result.scalar_one_or_none()
        if sim is None:
            raise NotFoundError(f"Simulation {sim_id} not found")
        if str(sim.criado_por) != str(ctx.user_id) and ctx.role.value not in ("manager", "admin"):
            raise TenantAccessError("Cannot archive another user's simulation")
        sim.status = SimulationStatus.arquivado
        sim.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return await self.get(sim.id, ctx)

    async def clone(self, sim_id: uuid.UUID, ctx: RequestContext) -> SimulationOut:
        original = await self.get(sim_id, ctx)
        codigo = await self._generate_codigo(ctx.tenant_id)
        new_sim = Simulation(
            tenant_id=ctx.tenant_id,
            codigo=codigo,
            cliente_nome=original.cliente_nome,
            veiculo_descricao=original.veiculo_descricao,
            valor_veiculo=original.valor_veiculo,
            valor_entrada=original.valor_entrada,
            valor_financiado=original.valor_financiado,
            taxa_mensal=original.taxa_mensal,
            prazo_meses=original.prazo_meses,
            data_liberacao=original.data_liberacao,
            primeiro_vencimento=original.primeiro_vencimento,
            incluir_iof=original.incluir_iof,
            iof_total=original.iof_total,
            parcela_financiamento=original.parcela_financiamento,
            total_pago=original.total_pago,
            total_juros=original.total_juros,
            cet_mensal=original.cet_mensal,
            cet_anual=original.cet_anual,
            status=SimulationStatus.rascunho,
            rules_snapshot_json=original.rules_snapshot_json or {},
            idempotency_key=None,
            criado_por=ctx.user_id,
        )
        self._s.add(new_sim)
        await self._s.flush()

        for fee in original.fees:
            self._s.add(SimulationFee(
                simulation_id=new_sim.id, tenant_id=ctx.tenant_id,
                nome=fee.nome, valor=fee.valor,
                incluir_no_principal=fee.incluir_no_principal,
            ))
        for extra in original.extras:
            self._s.add(SimulationExtra(
                simulation_id=new_sim.id, tenant_id=ctx.tenant_id,
                tipo=extra.tipo, nome=extra.nome, valor_total=extra.valor_total,
                modalidade=extra.modalidade, duracao_meses=extra.duracao_meses,
                valor_por_parcela=extra.valor_por_parcela, ordem=extra.ordem,
            ))
        for row in original.rows:
            self._s.add(AmortizationRow(
                simulation_id=new_sim.id, tenant_id=ctx.tenant_id,
                numero_parcela=row.numero_parcela,
                data_vencimento=row.data_vencimento,
                dias_periodo=row.dias_periodo,
                saldo_anterior=row.saldo_anterior,
                juros=row.juros,
                amortizacao=row.amortizacao,
                parcela=row.parcela,
                saldo_devedor=row.saldo_devedor,
                extras_total=row.extras_total,
                parcela_total=row.parcela_total,
                ajuste_arredondamento=row.ajuste_arredondamento,
            ))

        await self._s.flush()
        return await self.get(new_sim.id, ctx)
```

- [ ] **Step 3: Run all service tests**

```bash
cd backend && uv run pytest tests/test_simulation_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/services/simulation_service.py backend/tests/test_simulation_service.py
git commit -m "feat(services): add SimulationService create/get/list/update/archive/clone"
```

---

## Task 9: API routers

**Files:**

- Create: `backend/finacialsim_saas/api/business_rules.py`
- Create: `backend/finacialsim_saas/api/simulations.py`
- Modify: `backend/finacialsim_saas/main.py`

- [ ] **Step 1: Write failing endpoint tests**

Create `backend/tests/test_simulation_endpoints.py`:

```python
import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import date

from finacialsim_saas.data.models import Role, Tenant, User


async def _make_token(client, session, role=Role.user):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    from finacialsim_saas.data.models import Tenant

    t = Tenant(name=f"T-{uuid4().hex[:4]}", slug=f"t-{uuid4().hex[:6]}")
    session.add(t)
    await session.flush()

    from finacialsim_saas.cli.main import _seed_business_rules
    await _seed_business_rules(session, t.id)

    svc = AuthService(session, get_settings())
    email = f"ep-{uuid4().hex[:8]}@test.com"
    u = await svc.register_user(
        tenant_id=t.id, email=email, password="pass1234",
        name="Test", role=role,
    )
    await session.flush()
    tokens = await svc.issue_tokens(u)
    await session.commit()
    return tokens["access_token"], t, u


@pytest.mark.asyncio
async def test_get_business_rules(client, session):
    token, _, _ = await _make_token(client, session)
    resp = await client.get(
        "/api/v1/business-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "entrada_minima_pct" in data
    assert "taxa_por_prazo_curva" in data


@pytest.mark.asyncio
async def test_preview_returns_schedule(client, session):
    token, _, _ = await _make_token(client, session)
    resp = await client.post(
        "/api/v1/simulations/preview",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "valor_veiculo": "50000.00",
            "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199",
            "prazo_meses": 24,
            "data_liberacao": "2026-06-01",
            "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 24
    assert "summary" in data


@pytest.mark.asyncio
async def test_create_simulation_returns_201(client, session):
    token, _, _ = await _make_token(client, session)
    resp = await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "valor_veiculo": "50000.00",
            "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199",
            "prazo_meses": 24,
            "data_liberacao": "2026-06-01",
            "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["codigo"].startswith("SIM-")
    assert data["status"] == "confirmado"


@pytest.mark.asyncio
async def test_list_simulations_pagination(client, session):
    token, _, _ = await _make_token(client, session)
    for _ in range(3):
        await client.post(
            "/api/v1/simulations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
                "taxa_mensal": "0.0199", "prazo_meses": 24,
                "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
                "incluir_iof": False,
            },
        )
    resp = await client.get(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 3


@pytest.mark.asyncio
async def test_get_simulation_by_id(client, session):
    token, _, _ = await _make_token(client, session)
    created = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.get(
        f"/api/v1/simulations/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert len(resp.json()["rows"]) == 24


@pytest.mark.asyncio
async def test_cross_tenant_isolation(client, session):
    token_a, tenant_a, _ = await _make_token(client, session)
    token_b, _, _ = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.get(
        f"/api/v1/simulations/{sim['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clone_creates_rascunho(client, session):
    token, _, _ = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.post(
        f"/api/v1/simulations/{sim['id']}/clone",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "rascunho"
    assert resp.json()["id"] != sim["id"]


@pytest.mark.asyncio
async def test_archive_simulation(client, session):
    token, _, _ = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.post(
        f"/api/v1/simulations/{sim['id']}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "arquivado"
```

Run: `cd backend && uv run pytest tests/test_simulation_endpoints.py::test_get_business_rules -v`
Expected: FAIL with `404`

- [ ] **Step 2: Create `api/business_rules.py`**

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.business_rules import BusinessRulesOut, RateCurvePointOut
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
```

- [ ] **Step 3: Create `api/simulations.py`**

```python
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.simulations import (
    SimulationCreate, SimulationListPage, SimulationOut,
    SimulationPreviewRequest, SimulationPreviewResponse,
)
from finacialsim_saas.services.simulation_service import SimulationService

router = APIRouter(prefix="/api/v1", tags=["simulations"])


@router.post("/simulations/preview", response_model=SimulationPreviewResponse)
async def preview_simulation(
    body: SimulationPreviewRequest,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationPreviewResponse:
    svc = SimulationService(session)
    return await svc.preview(body, ctx)


@router.post("/simulations", response_model=SimulationOut, status_code=201)
async def create_simulation(
    body: SimulationCreate,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.create(body, ctx)
    await session.commit()
    return result


@router.get("/simulations", response_model=SimulationListPage)
async def list_simulations(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    cliente_nome: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> SimulationListPage:
    svc = SimulationService(session)
    return await svc.list(
        ctx, status=status, cliente_nome=cliente_nome,
        date_from=date_from, date_to=date_to, cursor=cursor, limit=limit,
    )


@router.get("/simulations/{sim_id}", response_model=SimulationOut)
async def get_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    return await svc.get(sim_id, ctx)


@router.patch("/simulations/{sim_id}", response_model=SimulationOut)
async def update_simulation(
    sim_id: uuid.UUID,
    body: SimulationCreate,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.update(sim_id, body, ctx)
    await session.commit()
    return result


@router.post("/simulations/{sim_id}/archive", response_model=SimulationOut)
async def archive_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.archive(sim_id, ctx)
    await session.commit()
    return result


@router.post("/simulations/{sim_id}/clone", response_model=SimulationOut, status_code=201)
async def clone_simulation(
    sim_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SimulationOut:
    svc = SimulationService(session)
    result = await svc.clone(sim_id, ctx)
    await session.commit()
    return result
```

- [ ] **Step 4: Wire routers in `main.py`**

Append to `backend/finacialsim_saas/main.py` (after the existing router includes):

```python
from finacialsim_saas.api.business_rules import router as business_rules_router  # noqa: E402
from finacialsim_saas.api.simulations import router as simulations_router        # noqa: E402

app.include_router(business_rules_router)
app.include_router(simulations_router)
```

- [ ] **Step 5: Run all endpoint tests**

```bash
cd backend && uv run pytest tests/test_simulation_endpoints.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/finacialsim_saas/api/business_rules.py \
        backend/finacialsim_saas/api/simulations.py \
        backend/finacialsim_saas/main.py \
        backend/tests/test_simulation_endpoints.py
git commit -m "feat(api): add business-rules and simulations endpoints"
```

---

## Self-Review

### Spec coverage

- [x] `business_rules` table — Task 1
- [x] `simulation_counters` — Task 1 (`SIM-YYYY-NNNNN` in Task 8)
- [x] `simulations` + child tables — Tasks 1–2
- [x] `extraordinary_amortizations` table created (no UI) — Task 1
- [x] `simulation_service.preview` — Tasks 7, 9
- [x] `simulation_service.create` with validation + snapshot — Task 8
- [x] `simulation_service.get/list/update/archive/clone` — Task 8
- [x] `rules_service.snapshot` — Task 6
- [x] All 7 API endpoints — Task 9
- [x] Cursor pagination — Task 8 (`list`)
- [x] Idempotency-Key — Task 8 (`create`)
- [x] Cross-tenant 404 — Task 8 + endpoint test
- [x] `user` PATCH own only; `manager`/`admin` any — Task 8 (`update`, `archive`)
- [x] CLI seeds `business_rules` on tenant create — Task 3
- [x] `DecimalStr` wire format — Task 4
- [x] Full rules snapshot — Task 8
- [x] `simulation_counters` row-lock `FOR UPDATE` — Task 8 (`_generate_codigo` via upsert)
- [x] Hard error on missing rules — Task 6

### Note on `_generate_codigo`

Uses `INSERT ... ON CONFLICT DO UPDATE RETURNING` (atomic upsert) instead of `SELECT FOR UPDATE` + update. This is equivalent and avoids the two-round-trip pattern — Postgres guarantees atomicity of the upsert.
