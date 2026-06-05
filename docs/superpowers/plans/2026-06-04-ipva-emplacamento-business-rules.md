# IPVA & Emplacamento — Configurable Business Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 per-tenant configurable business rule keys (IPVA % and emplacamento R$ by vehicle tipo), expose them in the Regras de Negócio admin UI, and pre-fill computed values when the user clicks "+ IPVA" or "+ Emplacamento" in the simulation form.

**Architecture:** Three-layer change: (1) Alembic data migration + backend service/schema, (2) admin UI new section, (3) frontend simulation form smart buttons. The frontend already fetches business rules via `useBusinessRules()` and vehicle data includes `tipo` — no new API endpoints needed.

**Tech Stack:** Python 3.12 / SQLAlchemy / Alembic (backend), React + TypeScript + React Hook Form + TanStack Query (frontend), pytest + asyncio (backend tests).

---

> ⚠️ **Deployment constraint:** Task 1 (migration) MUST run before Task 2 code goes live. Adding 6 keys to `_REQUIRED_RULES` means `get_rules()` raises for all tenants if the DB rows don't exist yet.

---

## File Map

| File | Action | Change |
|---|---|---|
| `backend/alembic/versions/010_seed_ipva_emplacamento_rules.py` | Create | Data migration: seed 6 rules for all existing tenants |
| `backend/finacialsim_saas/cli/main.py` | Modify | +6 entries in `_DEFAULT_BUSINESS_RULES` |
| `backend/finacialsim_saas/services/rules_service.py` | Modify | +6 keys in `_REQUIRED_RULES` |
| `backend/finacialsim_saas/schemas/business_rules.py` | Modify | +6 `DecimalStr` fields on `BusinessRulesOut` |
| `backend/tests/test_simulation_service.py` | Modify | Rename test + update `== 14` → `== 20` |
| `frontend/src/routes/simulacao/types.ts` | Modify | +6 string fields on `BusinessRules` interface |
| `frontend/src/routes/admin/BusinessRules.tsx` | Modify | +6 fields on `BusinessRulesData` + new "Extra / Rateio" section |
| `frontend/src/routes/simulacao/SimulacaoForm.tsx` | Modify | VehiclePicker passes `tipo`, `selectedVehicle` state, smart buttons |

---

## Task 1: Alembic migration — seed 6 new rules for all existing tenants

**Files:**
- Create: `backend/alembic/versions/010_seed_ipva_emplacamento_rules.py`

- [ ] **Step 1: Create the migration file**

```python
"""seed IPVA and emplacamento business rules for all tenants

Revision ID: 010
Revises: 009
Create Date: 2026-06-04
"""
import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

_NEW_RULES = [
    ("ipva_pct_carro",           "0.035",  "IPVA — alíquota carro (% a.a.)"),
    ("ipva_pct_moto",            "0.030",  "IPVA — alíquota moto (% a.a.)"),
    ("ipva_pct_caminhao",        "0.010",  "IPVA — alíquota caminhão (% a.a.)"),
    ("emplacamento_valor_carro",   "220.46", "Emplacamento — carro (R$)"),
    ("emplacamento_valor_moto",    "188.96", "Emplacamento — moto (R$)"),
    ("emplacamento_valor_caminhao","220.46", "Emplacamento — caminhão (R$)"),
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
            ).bindparams(chave=chave, valor=f'"{valor}"', descricao=descricao)
        )


def downgrade() -> None:
    for chave, _, _ in _NEW_RULES:
        op.execute(
            sa.text("DELETE FROM business_rules WHERE chave = :chave").bindparams(chave=chave)
        )
```

Note: `valor` is wrapped as `f'"{valor}"'` to produce a valid JSON string (e.g., `"0.035"`) for the JSONB column — consistent with how Python strings are stored by SQLAlchemy's JSONB column.

- [ ] **Step 2: Run the migration and verify**

```bash
cd backend && alembic upgrade head
```

Expected: `Running upgrade 009 -> 010` with no errors.

Verify with psql or a quick query (optional):
```bash
cd backend && python -c "
import asyncio
from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.settings import get_settings
from sqlalchemy import text

async def check():
    settings = get_settings()
    engine = build_engine(str(settings.database_url))
    factory = build_session_factory(engine)
    async with factory() as s:
        result = await s.execute(text(\"SELECT chave FROM business_rules WHERE chave LIKE 'ipva%' OR chave LIKE 'emplacamento_valor%' LIMIT 10\"))
        print([r[0] for r in result.all()])
    await engine.dispose()

asyncio.run(check())
"
```

Expected: 6 × (number of tenants) rows with the new `chave` values.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/010_seed_ipva_emplacamento_rules.py
git commit -m "feat(migration): seed IPVA and emplacamento business rules for existing tenants"
```

---

## Task 2: Backend — CLI defaults, required rules, Pydantic schema, test fix

**Files:**
- Modify: `backend/finacialsim_saas/cli/main.py`
- Modify: `backend/finacialsim_saas/services/rules_service.py`
- Modify: `backend/finacialsim_saas/schemas/business_rules.py`
- Modify: `backend/tests/test_simulation_service.py`

- [ ] **Step 1: Update the failing test first (TDD)**

In `backend/tests/test_simulation_service.py`, find:

```python
async def test_get_rules_returns_all_14_keys(session, tenant, rules_seeded):
    from finacialsim_saas.services.rules_service import RulesService
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert "entrada_minima_pct" in rules
    assert "taxa_por_prazo_curva" in rules
    assert len(rules) == 14
```

Replace with:

```python
async def test_get_rules_returns_all_20_keys(session, tenant, rules_seeded):
    from finacialsim_saas.services.rules_service import RulesService
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert "entrada_minima_pct" in rules
    assert "taxa_por_prazo_curva" in rules
    assert "ipva_pct_carro" in rules
    assert "emplacamento_valor_moto" in rules
    assert len(rules) == 20
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd backend && python -m pytest tests/test_simulation_service.py::test_get_rules_returns_all_20_keys -v
```

Expected: `FAILED` — `AssertionError: assert 14 == 20` (seed only has 14 entries so far).

- [ ] **Step 3: Add 6 entries to `_DEFAULT_BUSINESS_RULES` in `cli/main.py`**

In `backend/finacialsim_saas/cli/main.py`, append after the `rateio_emplacamento_meses_default` entry:

```python
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
    ("ipva_pct_carro",            "0.035",  "IPVA — alíquota carro (% a.a.)"),
    ("ipva_pct_moto",             "0.030",  "IPVA — alíquota moto (% a.a.)"),
    ("ipva_pct_caminhao",         "0.010",  "IPVA — alíquota caminhão (% a.a.)"),
    ("emplacamento_valor_carro",   "220.46", "Emplacamento — carro (R$)"),
    ("emplacamento_valor_moto",    "188.96", "Emplacamento — moto (R$)"),
    ("emplacamento_valor_caminhao","220.46", "Emplacamento — caminhão (R$)"),
]
```

- [ ] **Step 4: Add 6 keys to `_REQUIRED_RULES` in `rules_service.py`**

In `backend/finacialsim_saas/services/rules_service.py`, update:

```python
_REQUIRED_RULES = frozenset([
    "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
    "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
    "valor_minimo_financiado", "iof_fixo_pct", "iof_diario_pct",
    "iof_diario_max_dias", "incluir_iof_default",
    "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
    "taxa_por_prazo_curva",
    "ipva_pct_carro", "ipva_pct_moto", "ipva_pct_caminhao",
    "emplacamento_valor_carro", "emplacamento_valor_moto", "emplacamento_valor_caminhao",
])
```

- [ ] **Step 5: Add 6 fields to `BusinessRulesOut` in `schemas/business_rules.py`**

```python
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
    ipva_pct_carro: DecimalStr
    ipva_pct_moto: DecimalStr
    ipva_pct_caminhao: DecimalStr
    emplacamento_valor_carro: DecimalStr
    emplacamento_valor_moto: DecimalStr
    emplacamento_valor_caminhao: DecimalStr
```

- [ ] **Step 6: Run the test to confirm it passes**

```bash
cd backend && python -m pytest tests/test_simulation_service.py::test_get_rules_returns_all_20_keys -v
```

Expected: `PASSED`.

- [ ] **Step 7: Run the full backend test suite to check for regressions**

```bash
cd backend && python -m pytest --tb=short -q
```

Expected: all previously-passing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add backend/finacialsim_saas/cli/main.py \
        backend/finacialsim_saas/services/rules_service.py \
        backend/finacialsim_saas/schemas/business_rules.py \
        backend/tests/test_simulation_service.py
git commit -m "feat(backend): add IPVA and emplacamento configurable business rules"
```

---

## Task 3: Frontend types — add 6 fields to BusinessRules interfaces

**Files:**
- Modify: `frontend/src/routes/simulacao/types.ts`

- [ ] **Step 1: Add 6 fields to `BusinessRules` interface in `types.ts`**

In `frontend/src/routes/simulacao/types.ts`, update `BusinessRules`:

```typescript
export interface BusinessRules {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  dias_max_carencia: number;
  valor_minimo_financiado: string;
  iof_fixo_pct: string;
  iof_diario_pct: string;
  iof_diario_max_dias: number;
  incluir_iof_default: boolean;
  rateio_ipva_meses_default: number;
  rateio_emplacamento_meses_default: number;
  taxa_por_prazo_curva: RateCurvePoint[];
  ipva_pct_carro: string;
  ipva_pct_moto: string;
  ipva_pct_caminhao: string;
  emplacamento_valor_carro: string;
  emplacamento_valor_moto: string;
  emplacamento_valor_caminhao: string;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/simulacao/types.ts
git commit -m "feat(frontend/types): add IPVA and emplacamento fields to BusinessRules interface"
```

---

## Task 4: Admin UI — "Extra / Rateio" section in BusinessRules.tsx

**Files:**
- Modify: `frontend/src/routes/admin/BusinessRules.tsx`

- [ ] **Step 1: Add 6 fields to the local `BusinessRulesData` interface**

In `frontend/src/routes/admin/BusinessRules.tsx`, update `BusinessRulesData`:

```typescript
interface BusinessRulesData {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  valor_minimo_financiado: string;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  taxa_por_prazo_curva: RateCurvePoint[];
  iof_fixo_pct: string;
  iof_diario_pct: string;
  iof_diario_max_dias: number;
  incluir_iof_default: boolean;
  dias_max_carencia: number;
  rateio_ipva_meses_default: number;
  rateio_emplacamento_meses_default: number;
  ipva_pct_carro: string;
  ipva_pct_moto: string;
  ipva_pct_caminhao: string;
  emplacamento_valor_carro: string;
  emplacamento_valor_moto: string;
  emplacamento_valor_caminhao: string;
}
```

- [ ] **Step 2: Add the "Extra / Rateio" section between IOF and Padrões**

In the `return` block of `BusinessRules()`, insert after the closing `</section>` of the IOF section and before the opening `<section>` of the Padrões section:

```tsx
<section className="mb-8">
  <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Extra / Rateio</h2>
  <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
    <EditableField label="IPVA — Carro (%)" value={toDisplayPct(data.ipva_pct_carro, 2)} type="number" onSave={makePct("ipva_pct_carro")} motivo />
    <EditableField label="IPVA — Moto (%)" value={toDisplayPct(data.ipva_pct_moto, 2)} type="number" onSave={makePct("ipva_pct_moto")} motivo />
    <EditableField label="IPVA — Caminhão (%)" value={toDisplayPct(data.ipva_pct_caminhao, 2)} type="number" onSave={makePct("ipva_pct_caminhao")} motivo />
    <EditableField label="Emplacamento — Carro (R$)" value={String(data.emplacamento_valor_carro)} type="number" onSave={makeSave("emplacamento_valor_carro")} motivo />
    <EditableField label="Emplacamento — Moto (R$)" value={String(data.emplacamento_valor_moto)} type="number" onSave={makeSave("emplacamento_valor_moto")} motivo />
    <EditableField label="Emplacamento — Caminhão (R$)" value={String(data.emplacamento_valor_caminhao)} type="number" onSave={makeSave("emplacamento_valor_caminhao")} motivo />
  </div>
</section>
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/admin/BusinessRules.tsx
git commit -m "feat(admin): add Extra/Rateio section with IPVA and emplacamento rules"
```

---

## Task 5: Simulation form — VehiclePicker tipo, selectedVehicle state, smart buttons

**Files:**
- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx`

- [ ] **Step 1: Add `BusinessRules` to the import from `./types` in `SimulacaoForm.tsx`**

Find:

```tsx
import type { SimulationFormValues, PreviewPayload } from "./types";
```

Replace with:

```tsx
import type { SimulationFormValues, PreviewPayload, BusinessRules } from "./types";
```

- [ ] **Step 3: Extend `VehiclePicker` to pass `tipo` as third argument**

Find the `VehiclePicker` component declaration:

```tsx
function VehiclePicker({ value, onChange, error }: {
  value: string; onChange: (id: string, fipeValue: string | null) => void; error?: string;
}) {
```

Replace with:

```tsx
function VehiclePicker({ value, onChange, error }: {
  value: string; onChange: (id: string, fipeValue: string | null, tipo: string | null) => void; error?: string;
}) {
```

Then find the `onClick` inside the vehicle list map:

```tsx
onClick={() => {
  onChange(v.id, v.valor_fipe ?? v.valor_referencia ?? null);
  setQ(`${v.marca} ${v.modelo} ${v.ano_modelo}`);
}}
```

Replace with:

```tsx
onClick={() => {
  onChange(v.id, v.valor_fipe ?? v.valor_referencia ?? null, v.tipo ?? null);
  setQ(`${v.marca} ${v.modelo} ${v.ano_modelo}`);
}}
```

- [ ] **Step 4: Add `selectedVehicle` state to `SimulacaoForm`**

Inside `SimulacaoForm`, just after the `useFieldArray` declarations (around line 253), add:

```tsx
const [selectedVehicle, setSelectedVehicle] = useState<{
  fipeValue: string | null;
  tipo: string | null;
}>({ fipeValue: null, tipo: null });
```

- [ ] **Step 5: Wire `selectedVehicle` into the VehiclePicker call**

Find the existing `VehiclePicker` usage:

```tsx
<VehiclePicker
  value={watch("vehicle_id") ?? ""}
  onChange={(id, fipeValue) => {
    setValue("vehicle_id", id);
    if (fipeValue) setValue("valor_veiculo", fipeValue);
  }}
/>
```

Replace with:

```tsx
<VehiclePicker
  value={watch("vehicle_id") ?? ""}
  onChange={(id, fipeValue, tipo) => {
    setValue("vehicle_id", id);
    if (fipeValue) setValue("valor_veiculo", fipeValue);
    setSelectedVehicle({ fipeValue: fipeValue ?? null, tipo: tipo ?? null });
  }}
/>
```

- [ ] **Step 6: Update the "+ IPVA" button with smart pre-fill logic**

Find:

```tsx
<button
  type="button"
  className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
  onClick={() => appendExtra({
    tipo: "ipva", nome: "IPVA",
    valor_total: "0.00", modalidade: "rateio_meses",
    duracao_meses: rules?.rateio_ipva_meses_default ?? 12,
    ordem: extraFields.length,
  })}
>+ IPVA</button>
```

Replace with:

```tsx
<button
  type="button"
  className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
  onClick={() => {
    const tipoKey = `ipva_pct_${selectedVehicle.tipo}` as keyof BusinessRules;
    const ipvaPct = rules?.[tipoKey] as string | undefined;
    const fipe = selectedVehicle.fipeValue;
    const valorTotal =
      ipvaPct && fipe
        ? (parseFloat(fipe) * parseFloat(ipvaPct)).toFixed(2)
        : "0.00";
    appendExtra({
      tipo: "ipva",
      nome: "IPVA",
      valor_total: valorTotal,
      modalidade: "rateio_meses",
      duracao_meses: rules?.rateio_ipva_meses_default ?? 12,
      ordem: extraFields.length,
    });
  }}
>+ IPVA</button>
```

- [ ] **Step 7: Update the "+ Emplacamento" button with smart pre-fill logic**

Find:

```tsx
<button
  type="button"
  className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
  onClick={() => appendExtra({
    tipo: "emplacamento", nome: "Emplacamento",
    valor_total: "0.00", modalidade: "rateio_meses",
    duracao_meses: rules?.rateio_emplacamento_meses_default ?? 3,
    ordem: extraFields.length,
  })}
>+ Emplacamento</button>
```

Replace with:

```tsx
<button
  type="button"
  className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
  onClick={() => {
    const tipoKey = `emplacamento_valor_${selectedVehicle.tipo}` as keyof BusinessRules;
    const valorTotal = (rules?.[tipoKey] as string | undefined) ?? "0.00";
    appendExtra({
      tipo: "emplacamento",
      nome: "Emplacamento",
      valor_total: valorTotal,
      modalidade: "rateio_meses",
      duracao_meses: rules?.rateio_emplacamento_meses_default ?? 3,
      ordem: extraFields.length,
    });
  }}
>+ Emplacamento</button>
```

- [ ] **Step 8: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no type errors.

- [ ] **Step 9: Run frontend tests**

```bash
cd frontend && npm test -- --run
```

Expected: all tests pass.

- [ ] **Step 10: Manual smoke test**

Start the dev stack and verify:

1. Go to **Regras de Negócio** — confirm the new "Extra / Rateio" section appears with 6 editable fields showing default values (3.50%, 3.00%, 1.00%, 220.46, 188.96, 220.46).
2. Edit one value (e.g. IPVA Carro to 4.00) and save — confirm it persists on refresh.
3. Go to **Simulação** and select a vehicle that has a FIPE value and `tipo = "carro"`.
4. Click "+ IPVA" — confirm `valor_total` is pre-filled with `fipe_value × ipva_rate`.
5. Click "+ Emplacamento" — confirm `valor_total` is pre-filled with `220.46`.
6. Without selecting a vehicle first, click "+ IPVA" — confirm `valor_total` is `0.00`.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/routes/simulacao/SimulacaoForm.tsx
git commit -m "feat(simulacao): smart pre-fill for IPVA and emplacamento extras from business rules"
```
