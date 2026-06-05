# IPVA & Emplacamento — Configurable Business Rules

**Date:** 2026-06-04
**Status:** Approved
**Approach:** Frontend calculation (Approach A) + Smart button pre-fill

---

## Problem

IPVA percentage rates and emplacamento fixed values are hardcoded in comments/knowledge but not stored anywhere editable. Admins cannot update them, and the simulation form always inserts `valor_total: "0.00"` when the user clicks "+ IPVA" or "+ Emplacamento", requiring manual entry every time.

---

## Solution Overview

1. Add 6 new per-tenant `BusinessRule` keys for IPVA rates (% by tipo) and emplacamento amounts (R$ by tipo).
2. Seed defaults via CLI for new tenants and via Alembic migration for existing tenants.
3. Expose the 6 keys in a new "Extra / Rateio" section in the Regras de Negócio admin page.
4. In the simulation form, pre-fill `valor_total` when the user clicks "+ IPVA" or "+ Emplacamento", using the selected vehicle's `tipo` and FIPE value combined with the business rules. Values remain fully editable.

---

## Section 1 — New BusinessRule Keys

| Key | Type | Default | Admin label |
|---|---|---|---|
| `ipva_pct_carro` | decimal | 0.035 | IPVA — Carro (%) |
| `ipva_pct_moto` | decimal | 0.030 | IPVA — Moto (%) |
| `ipva_pct_caminhao` | decimal | 0.010 | IPVA — Caminhão (%) |
| `emplacamento_valor_carro` | decimal | 220.46 | Emplacamento — Carro (R$) |
| `emplacamento_valor_moto` | decimal | 188.96 | Emplacamento — Moto (R$) |
| `emplacamento_valor_caminhao` | decimal | 220.46 | Emplacamento — Caminhão (R$) |

Stored as JSONB in `business_rules`, one row per key per tenant — consistent with all existing rules.

### Backend files changed

| File | Change |
|---|---|
| `backend/finacialsim_saas/cli/main.py` | Append 6 entries to `_DEFAULT_BUSINESS_RULES` |
| `backend/finacialsim_saas/services/rules_service.py` | Append 6 keys to `_REQUIRED_RULES` |
| `backend/finacialsim_saas/schemas/business_rules.py` | Append 6 `DecimalStr` fields to `BusinessRulesOut` |
| `backend/alembic/versions/010_seed_ipva_emplacamento_rules.py` | New migration: `INSERT INTO business_rules ... ON CONFLICT DO NOTHING` for all existing tenants |

### Migration logic

```sql
INSERT INTO business_rules (id, tenant_id, chave, valor_json, descricao, atualizado_em)
SELECT gen_random_uuid(), t.id, :chave, :valor_json, :descricao, now()
FROM tenants t
ON CONFLICT (tenant_id, chave) DO NOTHING;
```
Run once per key (6 executions). Safe to re-run. Does not overwrite manually configured values.

---

## Section 2 — Admin UI: "Extra / Rateio" Section

New section added to `frontend/src/routes/admin/BusinessRules.tsx`, positioned between "IOF" and "Padrões".

```
Extra / Rateio
├── IPVA — Carro (%)             EditableField  percent  ipva_pct_carro
├── IPVA — Moto (%)              EditableField  percent  ipva_pct_moto
├── IPVA — Caminhão (%)          EditableField  percent  ipva_pct_caminhao
├── Emplacamento — Carro (R$)    EditableField  number   emplacamento_valor_carro
├── Emplacamento — Moto (R$)     EditableField  number   emplacamento_valor_moto
└── Emplacamento — Caminhão (R$) EditableField  number   emplacamento_valor_caminhao
```

IPVA % fields use `makePct()` (display as %, store as decimal, same as other rate fields).
Emplacamento R$ fields use `makeSave()` (stored as decimal string, displayed as-is).

The existing `rateio_ipva_meses_default` and `rateio_emplacamento_meses_default` remain in the "Padrões" section — they control duration of rateio, which is a separate concern.

### Frontend type changes

`BusinessRulesData` interface in `BusinessRules.tsx` and `BusinessRules` interface in `frontend/src/routes/simulacao/types.ts` both get the 6 new `string` fields.

---

## Section 3 — Simulation Form: Smart Buttons

### VehiclePicker signature change

```tsx
// before
onChange: (id: string, fipeValue: string | null) => void

// after
onChange: (id: string, fipeValue: string | null, tipo: string | null) => void
```

The vehicle list items already include `tipo`. This is passed through the existing picker dropdown's `onClick`.

### Selected vehicle local state

```tsx
const [selectedVehicle, setSelectedVehicle] = useState<{
  fipeValue: string | null;
  tipo: string | null;
}>({ fipeValue: null, tipo: null });
```

Updated in the `VehiclePicker.onChange` handler. Reset to `{ fipeValue: null, tipo: null }` when vehicle is cleared.

### Smart button logic

**+ IPVA clicked:**
```ts
const tipoKey = `ipva_pct_${selectedVehicle.tipo}` as keyof BusinessRules;
const ipvaPct = rules?.[tipoKey];
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
```

**+ Emplacamento clicked:**
```ts
const tipoKey = `emplacamento_valor_${selectedVehicle.tipo}` as keyof BusinessRules;
const valorTotal = rules?.[tipoKey] ?? "0.00";

appendExtra({
  tipo: "emplacamento",
  nome: "Emplacamento",
  valor_total: valorTotal,
  modalidade: "rateio_meses",
  duracao_meses: rules?.rateio_emplacamento_meses_default ?? 3,
  ordem: extraFields.length,
});
```

**Fallback:** If no vehicle is selected, `tipo` is null/unknown, or `fipeValue` is null → `valor_total` defaults to `"0.00"` (current behavior, unchanged).

---

## Files Changed

| File | Change |
|---|---|
| `backend/finacialsim_saas/cli/main.py` | +6 default business rules |
| `backend/finacialsim_saas/services/rules_service.py` | +6 required rule keys |
| `backend/finacialsim_saas/schemas/business_rules.py` | +6 fields on `BusinessRulesOut` |
| `backend/alembic/versions/010_seed_ipva_emplacamento_rules.py` | New migration |
| `frontend/src/routes/admin/BusinessRules.tsx` | New "Extra / Rateio" section + type fields |
| `frontend/src/routes/simulacao/types.ts` | +6 fields on `BusinessRules` interface |
| `frontend/src/routes/simulacao/SimulacaoForm.tsx` | VehiclePicker tipo, selectedVehicle state, smart buttons |

---

## Deployment Constraint

**The Alembic migration (`010_seed_ipva_emplacamento_rules.py`) must run before the new backend code goes live.** Adding 6 keys to `_REQUIRED_RULES` means `get_rules()` raises for every tenant if the DB rows don't exist yet. Standard migration-first deployment applies.

---

## Implementation Notes (from design review)

- **Storage format:** All 6 new keys stored as strings in JSONB (`"0.035"`, `"220.46"`), consistent with all existing decimal business rules.
- **IPVA display precision:** Pass `decimals=2` to `toDisplayPct()` for the 3 IPVA fields → shows `3.50%`, `3.00%`, `1.00%` (not 4 decimal places).
- **IPVA base value:** Uses `fipeValue` as already passed by `VehiclePicker` (`valor_fipe ?? valor_referencia`). No separate FIPE-only signal needed.
- **Test update:** `test_get_rules_returns_all_14_keys` must be renamed to `test_get_rules_returns_all_20_keys` and its `len(rules) == 14` assertion updated to `== 20`.
- **Edit mode:** `selectedVehicle` state initializes to `{ fipeValue: null, tipo: null }` regardless of `initialValues`. In edit mode, smart buttons fall back to `"0.00"` unless the user re-picks the vehicle. Acceptable limitation.

---

## Out of Scope

- "Reset to auto" button after manual override
- IPVA variation by state (currently flat per tipo)
- Emplacamento variation by year or UF
- Auto-adding IPVA/emplacamento when vehicle is selected (rejected in favour of smart buttons)
- Initializing `selectedVehicle` from `initialValues` in edit mode (requires an extra network call for a rare edge case)
