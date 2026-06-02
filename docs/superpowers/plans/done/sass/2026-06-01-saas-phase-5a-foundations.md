# Phase 5A — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate WeasyPrint on Linux, copy templates + utilities into the backend, define the sealed `PropostaSnapshot` Pydantic model with its builder, and run the Alembic migration for `proposals` + `parcela_payments`.

**Architecture:** All rendering assets live in `backend/finacialsim_saas/reports/`. Snapshot built once at proposal creation time from live DB objects; `PropostaSnapshot(extra="forbid")` enforces the snapshot boundary. Two new tables added via migration 006.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, WeasyPrint ≥62, Jinja2 ≥3.1, uv

---

## Prerequisites

- Phase 4 merged and tests green
- `cd backend && uv sync --extra dev` passes
- Running Postgres (testcontainers handles this in tests)

---

## Task 0: WeasyPrint Linux smoke test (BLOCKER — complete before proceeding)

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Create: `backend/smoke_weasyprint.py` (delete after Task 0 passes)

- [ ] **Step 0.1 — Add WeasyPrint + Jinja2 to backend deps**

Edit `backend/pyproject.toml`, add to `dependencies`:
```toml
"weasyprint>=62.0",
"jinja2>=3.1.0",
```

- [ ] **Step 0.2 — Sync deps**

```bash
cd /home/fj/git/financialsim-saas
uv sync --extra dev
```
Expected: no errors. WeasyPrint installs with system-dep bindings.

- [ ] **Step 0.3 — Write smoke script**

Create `backend/smoke_weasyprint.py`:
```python
"""Run once locally to verify WeasyPrint renders on Linux. Delete after passing."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

REPORTS = Path(__file__).parent / "finacialsim_saas" / "reports"
env = Environment(loader=FileSystemLoader(str(REPORTS)), autoescape=True)

ctx = {
    "loja": {"nome": "Loja Teste", "cnpj": None, "telefone": None, "endereco": None},
    "vendedor": {"nome": "Vendedor Teste"},
    "proposal": {"codigo": "PROP-2026-00001", "gerado_em_br": "01/06/2026", "validade_dias": 7},
    "cliente": {"nome": "João Silva", "tipo": "PF", "cpf_cnpj_fmt": "123.456.789-09", "telefone": None},
    "veiculo": {"marca": "Toyota", "modelo": "Corolla", "ano_modelo": 2022,
                "codigo_fipe": "005004-9", "mes_referencia_fipe": "maio/2026"},
    "sim": {
        "valor_veiculo_brl": "R$ 85.000,00",
        "valor_financiado_brl": "R$ 68.000,00",
        "valor_entrada_brl": "R$ 17.000,00",
        "pct_entrada_pct": "20,00%",
        "prazo_meses": 48,
        "taxa_juros_mes_pct": "1,2900%",
        "taxa_juros_ano_pct": "16,63%",
        "cet_mes_pct": "1,3500%",
        "cet_ano_pct": "17,45%",
        "incluir_iof": True,
        "iof_total_brl": "R$ 1.224,00",
        "tarifas_total_brl": "R$ 500,00",
        "valor_parcela_brl": "R$ 1.987,34",
        "parcela_total_1ano_brl": "R$ 2.087,34",
        "parcela_total_apos_brl": "R$ 1.987,34",
        "total_pago_brl": "R$ 95.392,32",
        "total_juros_brl": "R$ 27.392,32",
        "pct_juros_pct": "40,28%",
        "total_pago_cliente_brl": "R$ 95.392,32",
    },
    "extras": [],
    "cronograma": [
        {
            "numero": i,
            "venc": f"0{i}/07/2026" if i < 10 else f"{i}/07/2026",
            "juros_brl": "R$ 877,20",
            "amortizacao_brl": "R$ 1.110,14",
            "parcela_brl": "R$ 1.987,34",
            "extras_brl": "R$ 0,00",
            "parcela_total_brl": "R$ 1.987,34",
            "saldo_brl": f"R$ {68000 - i * 1110:.2f}".replace(".", ","),
        }
        for i in range(1, 5)
    ],
}

# Render proposta
template = env.get_template("proposta.html")
html = template.render(**ctx)
css_path = REPORTS / "proposta.css"
stylesheets = [CSS(filename=str(css_path))] if css_path.exists() else []
pdf = HTML(string=html).write_pdf(stylesheets=stylesheets)
assert len(pdf) > 1000, "proposta PDF too small — render likely failed"
print(f"proposta.html → {len(pdf):,} bytes OK")

# Render carne
carne_ctx = {
    "loja": ctx["loja"],
    "proposal": {"codigo": "PROP-2026-00001"},
    "cliente": {"nome": "João Silva", "cpf_cnpj_fmt": "123.456.789-09"},
    "veiculo": {"descricao": "Toyota Corolla (2022)", "placa": "ABC-1234"},
    "parcelas": [
        {"numero": i, "total": 48, "vencimento_br": f"0{i}/07/2026", "valor_total_brl": "R$ 1.987,34"}
        for i in range(1, 5)
    ],
}
template_c = env.get_template("carne.html")
html_c = template_c.render(**carne_ctx)
css_c = REPORTS / "carne.css"
stylesheets_c = [CSS(filename=str(css_c))] if css_c.exists() else []
pdf_c = HTML(string=html_c).write_pdf(stylesheets=stylesheets_c)
assert len(pdf_c) > 1000, "carne PDF too small"
print(f"carne.html → {len(pdf_c):,} bytes OK")

print("WeasyPrint smoke test PASSED")
```

- [ ] **Step 0.4 — Copy templates + CSS from finacialsim_core**

```bash
mkdir -p /home/fj/git/financialsim-saas/backend/finacialsim_saas/reports
cp /home/fj/git/financialsim-saas/packages/finacialsim_core/finacialsim_core/reports/proposta.html \
   /home/fj/git/financialsim-saas/backend/finacialsim_saas/reports/
cp /home/fj/git/financialsim-saas/packages/finacialsim_core/finacialsim_core/reports/carne.html \
   /home/fj/git/financialsim-saas/backend/finacialsim_saas/reports/
cp /home/fj/git/financialsim-saas/app/reports/proposta.css \
   /home/fj/git/financialsim-saas/backend/finacialsim_saas/reports/
cp /home/fj/git/financialsim-saas/app/reports/carne.css \
   /home/fj/git/financialsim-saas/backend/finacialsim_saas/reports/
```

- [ ] **Step 0.5 — Run smoke test locally**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run python smoke_weasyprint.py
```
Expected output:
```
proposta.html → <N> bytes OK
carne.html → <N> bytes OK
WeasyPrint smoke test PASSED
```

**If this fails:** Do not proceed. Fix template rendering issues first. Common causes: missing CSS file path, Jinja2 variable mismatch.

- [ ] **Step 0.6 — Delete smoke script**

```bash
rm /home/fj/git/financialsim-saas/backend/smoke_weasyprint.py
```

- [ ] **Step 0.7 — Add WeasyPrint system deps to CI**

Edit `.github/workflows/ci.yml`. Add a step BEFORE `uv sync` in the `backend` job:
```yaml
      - name: Install WeasyPrint system deps
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends
          libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
```

- [ ] **Step 0.8 — Commit**

```bash
git add backend/pyproject.toml \
        backend/finacialsim_saas/reports/ \
        .github/workflows/ci.yml
git commit -m "feat(phase5): add WeasyPrint dep + copy report templates to backend"
```

---

## Task 1: br_format utilities

**Files:**
- Create: `backend/finacialsim_saas/utils/__init__.py`
- Create: `backend/finacialsim_saas/utils/br_format.py`
- Test: `backend/tests/test_br_format.py`

- [ ] **Step 1.1 — Write the failing test**

Create `backend/tests/test_br_format.py`:
```python
import pytest
from decimal import Decimal
from datetime import date

from finacialsim_saas.utils.br_format import (
    format_brl, format_pct, format_date_br, format_cpf_cnpj,
)


def test_format_brl_basic():
    assert format_brl(Decimal("1234.56")) == "R$ 1.234,56"


def test_format_brl_negative():
    assert format_brl(Decimal("-100.00")) == "-R$ 100,00"


def test_format_brl_large():
    assert format_brl(Decimal("1000000.00")) == "R$ 1.000.000,00"


def test_format_pct_default():
    # 0.0189 → "1,89%"
    assert format_pct(Decimal("0.0189")) == "1,89%"


def test_format_pct_4_decimals():
    assert format_pct(Decimal("0.01290"), 4) == "1,2900%"


def test_format_date_br():
    assert format_date_br(date(2026, 6, 1)) == "01/06/2026"


def test_format_cpf_pf():
    assert format_cpf_cnpj("12345678909", "PF") == "123.456.789-09"


def test_format_cpf_pj():
    assert format_cpf_cnpj("12345678000195", "PJ") == "12.345.678/0001-95"


def test_format_cpf_invalid_passthrough():
    assert format_cpf_cnpj("123", "PF") == "123"
```

- [ ] **Step 1.2 — Run to verify failure**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_br_format.py -v
```
Expected: `ModuleNotFoundError: No module named 'finacialsim_saas.utils'`

- [ ] **Step 1.3 — Create utils package + module**

Create `backend/finacialsim_saas/utils/__init__.py` (empty):
```python
```

Create `backend/finacialsim_saas/utils/br_format.py`:
```python
"""Brazilian display formatters: R$, %, dd/mm/yyyy, CPF/CNPJ."""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def format_brl(value: Decimal) -> str:
    """Format Decimal as 'R$ 1.234,56'."""
    negative = value < 0
    abs_val = abs(value)
    integer, _, decimals = f"{abs_val:.2f}".partition(".")
    chunks: list[str] = []
    while len(integer) > 3:
        chunks.append(integer[-3:])
        integer = integer[:-3]
    chunks.append(integer)
    formatted_int = ".".join(reversed(chunks))
    sign = "-" if negative else ""
    return f"{sign}R$ {formatted_int},{decimals}"


def format_pct(value: Decimal, decimals: int = 2) -> str:
    """Format 0.0189 → '1,89%'."""
    pct = value * Decimal("100")
    s = f"{pct:.{decimals}f}".replace(".", ",")
    return f"{s}%"


def format_date_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_cpf_cnpj(s: str, tipo: str) -> str:
    if tipo == "PF" and len(s) == 11:
        return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
    if tipo == "PJ" and len(s) == 14:
        return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"
    return s
```

- [ ] **Step 1.4 — Run test to verify it passes**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_br_format.py -v
```
Expected: all 9 tests PASS

- [ ] **Step 1.5 — Commit**

```bash
git add backend/finacialsim_saas/utils/ backend/tests/test_br_format.py
git commit -m "feat(phase5): add br_format utility (BRL, pct, date, CPF/CNPJ formatters)"
```

---

## Task 2: PropostaSnapshot model + build_snapshot

**Files:**
- Create: `backend/finacialsim_saas/schemas/proposals.py`
- Test: `backend/tests/test_proposal_snapshot.py`

- [ ] **Step 2.1 — Write the failing test**

Create `backend/tests/test_proposal_snapshot.py`:
```python
import uuid
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from finacialsim_saas.data.models import (
    AmortizationRow, Client, ClientType, Simulation, SimulationExtra,
    SimulationFee, SimulationStatus, Tenant, User, Role,
)
from finacialsim_saas.schemas.proposals import PropostaSnapshot, build_snapshot


def _make_sim() -> Simulation:
    s = MagicMock(spec=Simulation)
    s.tenant_id = uuid.uuid4()
    s.id = uuid.uuid4()
    s.client_id = None
    s.vehicle_id = None
    s.valor_veiculo = Decimal("85000.00")
    s.valor_entrada = Decimal("17000.00")
    s.valor_financiado = Decimal("68000.00")
    s.taxa_mensal = Decimal("0.012900")
    s.prazo_meses = 48
    s.data_liberacao = date(2026, 6, 1)
    s.primeiro_vencimento = date(2026, 7, 1)
    s.incluir_iof = True
    s.iof_total = Decimal("1224.00")
    s.parcela_financiamento = Decimal("1987.34")
    s.total_pago = Decimal("95392.32")
    s.total_juros = Decimal("27392.32")
    s.cet_mensal = Decimal("0.013500")
    s.cet_anual = Decimal("0.174500")
    s.status = SimulationStatus.confirmado
    return s


def _make_tenant() -> Tenant:
    t = MagicMock(spec=Tenant)
    t.id = uuid.uuid4()
    t.name = "Financiadora Teste"
    return t


def _make_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.name = "Vendedor Teste"
    u.role = Role.user
    return u


def _make_row(num: int) -> AmortizationRow:
    r = MagicMock(spec=AmortizationRow)
    r.numero_parcela = num
    r.data_vencimento = date(2026, 7, num)
    r.juros = Decimal("877.20")
    r.amortizacao = Decimal("1110.14")
    r.parcela = Decimal("1987.34")
    r.extras_total = Decimal("0.00")
    r.parcela_total = Decimal("1987.34")
    r.saldo_devedor = Decimal("68000.00") - num * Decimal("1110.14")
    return r


def test_build_snapshot_basic():
    snap = build_snapshot(
        sim=_make_sim(),
        fees=[],
        extras=[],
        rows=[_make_row(1), _make_row(2)],
        client=None,
        vehicle=None,
        tenant=_make_tenant(),
        user=_make_user(),
    )
    assert isinstance(snap, PropostaSnapshot)
    assert snap.loja.nome == "Financiadora Teste"
    assert snap.vendedor.nome == "Vendedor Teste"
    assert snap.cliente is None
    assert snap.veiculo is None
    assert snap.sim.prazo_meses == 48
    assert len(snap.cronograma) == 2
    assert snap.cronograma[0].venc == "2026-07-01"


def test_build_snapshot_tarifas_computed():
    fee = MagicMock(spec=SimulationFee)
    fee.valor = Decimal("300.00")
    fee2 = MagicMock(spec=SimulationFee)
    fee2.valor = Decimal("200.00")
    snap = build_snapshot(
        sim=_make_sim(), fees=[fee, fee2], extras=[],
        rows=[_make_row(1)], client=None, vehicle=None,
        tenant=_make_tenant(), user=_make_user(),
    )
    assert snap.sim.tarifas_total == "500.00"


def test_snapshot_rejects_extra_fields():
    """extra='forbid' means Pydantic raises on unknown keys."""
    with pytest.raises(Exception):
        PropostaSnapshot.model_validate({
            "loja": {"nome": "X", "unknown_field": "boom"},
            "vendedor": {"nome": "V"},
            "sim": {},
            "extras": [],
            "cronograma": [],
        })


def test_snapshot_roundtrip_json():
    snap = build_snapshot(
        sim=_make_sim(), fees=[], extras=[],
        rows=[_make_row(1)], client=None, vehicle=None,
        tenant=_make_tenant(), user=_make_user(),
    )
    dumped = snap.model_dump()
    restored = PropostaSnapshot.model_validate(dumped)
    assert restored.sim.prazo_meses == snap.sim.prazo_meses
```

- [ ] **Step 2.2 — Run to verify failure**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_proposal_snapshot.py -v
```
Expected: `ImportError` — `schemas/proposals.py` doesn't exist yet.

- [ ] **Step 2.3 — Create schemas/proposals.py**

Create `backend/finacialsim_saas/schemas/proposals.py`:
```python
"""Proposal schemas: PropostaSnapshot (sealed) + API request/response models."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from finacialsim_core.money import quantize_brl
from finacialsim_saas.data.models import (
    AmortizationRow, Client, ClientType, Simulation,
    SimulationExtra, SimulationFee, Tenant, User, Vehicle,
)


# ── Snapshot sub-models (extra="forbid" seals the contract) ──────────────────

class LojaSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    endereco: str | None = None


class VendedorSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str


class ClienteSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    tipo: str  # "PF" | "PJ"
    cpf_cnpj: str  # raw digits, no mask
    telefone: str | None = None


class VeiculoSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marca: str
    modelo: str
    ano_modelo: int
    descricao: str
    placa: str | None = None
    codigo_fipe: str | None = None
    mes_referencia_fipe: str | None = None


class SimSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor_veiculo: str       # Decimal as str
    valor_entrada: str
    valor_financiado: str
    prazo_meses: int
    taxa_mensal: str         # e.g. "0.012900"
    taxa_anual: str          # (1+taxa_mensal)^12 - 1
    incluir_iof: bool
    iof_total: str
    tarifas_total: str       # sum of all simulation_fees.valor
    valor_parcela: str       # parcela_financiamento
    total_pago: str
    total_juros: str
    cet_mensal: str
    cet_anual: str
    extras_acumulado: str    # sum of amortization_rows.extras_total


class ExtraSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    modalidade: str          # raw value e.g. "mensal_continuo"
    valor_total: str
    duracao_meses: int
    valor_por_parcela: str


class CronogramaRowSnap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero: int
    venc: str                # ISO date "YYYY-MM-DD"
    juros: str
    amortizacao: str
    parcela: str
    extras: str
    parcela_total: str
    saldo: str


class PropostaSnapshot(BaseModel):
    """Sealed snapshot — extra fields rejected. Render reads only this."""
    model_config = ConfigDict(extra="forbid")
    loja: LojaSnap
    vendedor: VendedorSnap
    cliente: ClienteSnap | None = None
    veiculo: VeiculoSnap | None = None
    sim: SimSnap
    extras: list[ExtraSnap]
    cronograma: list[CronogramaRowSnap]


# ── Snapshot builder ──────────────────────────────────────────────────────────

def _d(v: object) -> Decimal:
    return Decimal(str(v))


def build_snapshot(
    sim: Simulation,
    fees: list[SimulationFee],
    extras: list[SimulationExtra],
    rows: list[AmortizationRow],
    client: Client | None,
    vehicle: Vehicle | None,
    tenant: Tenant,
    user: User,
) -> PropostaSnapshot:
    tarifas_total = sum((_d(f.valor) for f in fees), Decimal("0.00"))
    extras_acumulado = sum((_d(r.extras_total) for r in rows), Decimal("0.00"))
    taxa_anual = (1 + _d(sim.taxa_mensal)) ** 12 - 1

    cliente_snap = None
    if client is not None:
        tipo = "PF" if client.tipo == ClientType.pf else "PJ"
        cliente_snap = ClienteSnap(
            nome=client.nome,
            tipo=tipo,
            cpf_cnpj=client.cpf_cnpj,
            telefone=client.telefone,
        )

    veiculo_snap = None
    if vehicle is not None:
        veiculo_snap = VeiculoSnap(
            marca=vehicle.marca,
            modelo=vehicle.modelo,
            ano_modelo=vehicle.ano_modelo,
            descricao=f"{vehicle.marca} {vehicle.modelo} ({vehicle.ano_modelo})",
            placa=vehicle.placa,
            codigo_fipe=vehicle.codigo_fipe,
            mes_referencia_fipe=vehicle.mes_referencia_fipe,
        )

    return PropostaSnapshot(
        loja=LojaSnap(nome=tenant.name),
        vendedor=VendedorSnap(nome=user.name),
        cliente=cliente_snap,
        veiculo=veiculo_snap,
        sim=SimSnap(
            valor_veiculo=str(sim.valor_veiculo),
            valor_entrada=str(sim.valor_entrada),
            valor_financiado=str(sim.valor_financiado),
            prazo_meses=sim.prazo_meses,
            taxa_mensal=str(sim.taxa_mensal),
            taxa_anual=str(quantize_brl(taxa_anual)),
            incluir_iof=sim.incluir_iof,
            iof_total=str(sim.iof_total),
            tarifas_total=str(quantize_brl(tarifas_total)),
            valor_parcela=str(sim.parcela_financiamento),
            total_pago=str(sim.total_pago),
            total_juros=str(sim.total_juros),
            cet_mensal=str(sim.cet_mensal),
            cet_anual=str(sim.cet_anual),
            extras_acumulado=str(quantize_brl(extras_acumulado)),
        ),
        extras=[
            ExtraSnap(
                nome=e.nome,
                modalidade=e.modalidade,
                valor_total=str(e.valor_total),
                duracao_meses=e.duracao_meses,
                valor_por_parcela=str(e.valor_por_parcela),
            )
            for e in extras
        ],
        cronograma=[
            CronogramaRowSnap(
                numero=r.numero_parcela,
                venc=r.data_vencimento.isoformat(),
                juros=str(r.juros),
                amortizacao=str(r.amortizacao),
                parcela=str(r.parcela),
                extras=str(r.extras_total),
                parcela_total=str(r.parcela_total),
                saldo=str(r.saldo_devedor),
            )
            for r in rows
        ],
    )


# ── API request/response schemas ──────────────────────────────────────────────

class ProposalCreate(BaseModel):
    simulation_id: uuid.UUID


class ProposalOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    simulation_id: uuid.UUID
    codigo: str
    gerado_por: uuid.UUID
    gerado_em: datetime
    validade_dias: int
    render_status: str
    render_error: str | None
    status: str
    pdf_key: str | None
    carne_key: str | None
    aprovado_por: uuid.UUID | None
    aprovado_em: datetime | None
    cancelado_por: uuid.UUID | None
    cancelado_em: datetime | None


class ProposalListItem(BaseModel):
    id: uuid.UUID
    codigo: str
    simulation_id: uuid.UUID
    render_status: str
    status: str
    gerado_em: datetime


class ProposalListPage(BaseModel):
    items: list[ProposalListItem]
    next_cursor: str | None
```

- [ ] **Step 2.4 — Run tests**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_proposal_snapshot.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 2.5 — Commit**

```bash
git add backend/finacialsim_saas/schemas/proposals.py \
        backend/tests/test_proposal_snapshot.py
git commit -m "feat(phase5): PropostaSnapshot model + build_snapshot builder"
```

---

## Task 3: Settings update

**Files:**
- Modify: `backend/finacialsim_saas/settings.py`
- Test: `backend/tests/test_settings.py` (existing file — add assertions)

- [ ] **Step 3.1 — Update settings**

Edit `backend/finacialsim_saas/settings.py`. Add three new fields to `Settings`:
```python
    storage_backend: str = "local"              # "local" | "s3"
    storage_local_root: str = "./storage"       # overridden to /data/proposals in Docker
    storage_hmac_secret: str = "change-storage-secret-in-production"
    storage_base_url: str = "http://localhost:8000"  # signed URL host for local backend
```

- [ ] **Step 3.2 — Verify existing settings tests still pass**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_settings.py -v
```
Expected: PASS (new fields have defaults, so existing tests unaffected).

- [ ] **Step 3.3 — Commit**

```bash
git add backend/finacialsim_saas/settings.py
git commit -m "feat(phase5): add storage settings (backend, local_root, hmac_secret, base_url)"
```

---

## Task 4: Alembic migration + ORM models

**Files:**
- Modify: `backend/finacialsim_saas/data/models.py`
- Create: `backend/alembic/versions/006_proposals.py`
- Test: `backend/tests/test_models.py` (existing — add assertions)

- [ ] **Step 4.1 — Add ORM models**

Open `backend/finacialsim_saas/data/models.py`. After the `Vehicle` model block (end of file), add:

```python
class ProposalRenderStatus(enum.Enum):
    pending = "pending"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


class ProposalStatus(enum.Enum):
    rascunho = "rascunho"
    ready = "ready"
    aprovada = "aprovada"
    cancelada = "cancelada"


class ParcelaPaymentStatus(enum.Enum):
    pending = "pending"
    paid = "paid"
    canceled = "canceled"


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("simulations.id"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(sa.Text, nullable=False)
    gerado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    gerado_em: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    validade_dias: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("7")
    )
    snapshot_json: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    pdf_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    carne_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    render_status: Mapped[ProposalRenderStatus] = mapped_column(
        sa.Enum(ProposalRenderStatus, name="proposal_render_status", native_enum=True),
        nullable=False, server_default=sa.text("'pending'"),
    )
    render_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(
        sa.Enum(ProposalStatus, name="proposal_status", native_enum=True),
        nullable=False, server_default=sa.text("'rascunho'"),
    )
    aprovado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aprovado_em: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    cancelado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_proposals_tenant_codigo"),
        sa.UniqueConstraint("tenant_id", "simulation_id", name="uq_proposals_tenant_simulation"),
        sa.Index("ix_proposals_tenant_gerado_em", "tenant_id", "gerado_em"),
    )


class ParcelaPayment(Base):
    __tablename__ = "parcela_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    parcela_num: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    vencimento: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    valor_parcela: Mapped[Decimal] = mapped_column(sa.Numeric(18, 2), nullable=False)
    status: Mapped[ParcelaPaymentStatus] = mapped_column(
        sa.Enum(ParcelaPaymentStatus, name="parcela_payment_status", native_enum=True),
        nullable=False, server_default=sa.text("'pending'"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    pix_charge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        sa.Index("ix_parcela_payments_proposal_num", "proposal_id", "parcela_num"),
    )
```

- [ ] **Step 4.2 — Write migration 006_proposals.py**

Create `backend/alembic/versions/006_proposals.py`:
```python
"""proposals and parcela_payments tables

Revision ID: 006
Revises: 005
Create Date: 2026-06-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE proposal_render_status AS ENUM "
        "('pending', 'rendering', 'ready', 'failed')"
    )
    op.execute(
        "CREATE TYPE proposal_status AS ENUM "
        "('rascunho', 'ready', 'aprovada', 'cancelada')"
    )
    op.execute(
        "CREATE TYPE parcela_payment_status AS ENUM "
        "('pending', 'paid', 'canceled')"
    )

    op.create_table(
        "proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("simulation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("simulations.id"), nullable=False),
        sa.Column("codigo", sa.Text, nullable=False),
        sa.Column("gerado_por", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("gerado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("validade_dias", sa.Integer,
                  server_default=sa.text("7"), nullable=False),
        sa.Column("snapshot_json", sa.JSON, nullable=False),
        sa.Column("pdf_key", sa.Text, nullable=True),
        sa.Column("carne_key", sa.Text, nullable=True),
        sa.Column("render_status",
                  sa.Enum("pending", "rendering", "ready", "failed",
                          name="proposal_render_status", create_type=False),
                  server_default=sa.text("'pending'"), nullable=False),
        sa.Column("render_error", sa.Text, nullable=True),
        sa.Column("status",
                  sa.Enum("rascunho", "ready", "aprovada", "cancelada",
                          name="proposal_status", create_type=False),
                  server_default=sa.text("'rascunho'"), nullable=False),
        sa.Column("aprovado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_proposals_tenant_codigo", "proposals", ["tenant_id", "codigo"]
    )
    op.create_unique_constraint(
        "uq_proposals_tenant_simulation", "proposals", ["tenant_id", "simulation_id"]
    )
    op.create_index("ix_proposals_tenant_gerado_em", "proposals",
                    ["tenant_id", "gerado_em"])

    op.create_table(
        "parcela_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parcela_num", sa.Integer, nullable=False),
        sa.Column("vencimento", sa.Date, nullable=False),
        sa.Column("valor_parcela", sa.Numeric(18, 2), nullable=False),
        sa.Column("status",
                  sa.Enum("pending", "paid", "canceled",
                          name="parcela_payment_status", create_type=False),
                  server_default=sa.text("'pending'"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pix_charge_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_parcela_payments_proposal_num", "parcela_payments",
                    ["proposal_id", "parcela_num"])


def downgrade() -> None:
    op.drop_table("parcela_payments")
    op.drop_table("proposals")
    op.execute("DROP TYPE IF EXISTS parcela_payment_status")
    op.execute("DROP TYPE IF EXISTS proposal_status")
    op.execute("DROP TYPE IF EXISTS proposal_render_status")
```

- [ ] **Step 4.3 — Verify existing model tests pass (new models importable)**

```bash
cd /home/fj/git/financialsim-saas/backend
uv run pytest tests/test_models.py -v
```
Expected: PASS (existing tests unaffected; new models just added).

- [ ] **Step 4.4 — Commit**

```bash
git add backend/finacialsim_saas/data/models.py \
        backend/alembic/versions/006_proposals.py
git commit -m "feat(phase5): add Proposal + ParcelaPayment ORM models and migration 006"
```

---

## Phase 5A complete

All foundations are in place. Proceed to `2026-06-01-saas-phase-5b-services.md`.
