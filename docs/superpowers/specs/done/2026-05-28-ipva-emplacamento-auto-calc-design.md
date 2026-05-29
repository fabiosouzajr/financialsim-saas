# Design Spec — IPVA & Emplacamento Auto-Calculation

**Date:** 2026-05-28
**Status:** Approved
**Approach:** Auto-fill on vehicle selection (Approach A)

---

## Problem

IPVA and emplacamento values in the Simulação form are currently entered manually by the user. They should be auto-calculated from the selected vehicle's tipo and FIPE value, using admin-configurable rates stored in Regras de Negócio.

---

## Solution Overview

1. Add 6 new `BusinessRule` keys for IPVA rates (% per tipo) and emplacamento fixed values (R$ per tipo).
2. Seed those keys with default values via an Alembic data migration.
3. Expose all 6 in the "Extras / Rateio" section of Configurações.
4. In Simulação, auto-fill the IPVA and emplacamento fields when a vehicle is selected. Fields remain editable for manual override.

---

## Section 1 — New BusinessRule Keys

| Key | Type | Default | Configurações label |
|---|---|---|---|
| `ipva_pct_carro` | percent | 0.035 | IPVA — carro (%) |
| `ipva_pct_moto` | percent | 0.030 | IPVA — moto (%) |
| `ipva_pct_caminhao` | percent | 0.010 | IPVA — caminhão (%) |
| `emplacamento_valor_carro` | currency | 220.46 | Emplacamento — carro (R$) |
| `emplacamento_valor_moto` | currency | 188.96 | Emplacamento — moto (R$) |
| `emplacamento_valor_caminhao` | currency | 220.46 | Emplacamento — caminhão (R$) |

Seeded via `INSERT OR IGNORE` in a new Alembic migration so defaults appear on first run without requiring a manual save in Configurações.

---

## Section 2 — Configurações Changes (`app/ui/pages/configuracoes.py`)

- **`EDITABLE_KEYS`**: append all 6 new keys.
- **`LABEL_MAP`**: add labels per table above.
- **`PCT_KEYS`**: add `ipva_pct_carro`, `ipva_pct_moto`, `ipva_pct_caminhao` → rendered as `PercentInput`.
- **`CURRENCY_KEYS`**: add `emplacamento_valor_carro`, `emplacamento_valor_moto`, `emplacamento_valor_caminhao` → rendered as `CurrencyInput`.
- **`GROUPS["Extras / Rateio"]`**: expand key list from 2 to 8 fields:

```
Extras / Rateio
  ├── rateio_ipva_meses_default          (existing)
  ├── rateio_emplacamento_meses_default  (existing)
  ├── ipva_pct_carro                     (new)
  ├── ipva_pct_moto                      (new)
  ├── ipva_pct_caminhao                  (new)
  ├── emplacamento_valor_carro           (new)
  ├── emplacamento_valor_moto            (new)
  └── emplacamento_valor_caminhao        (new)
```

No other sections or files in Configurações are touched.

---

## Section 3 — Simulação Auto-Fill (`app/ui/pages/simulacao.py`)

### Trigger points

**Vehicle selected** (`_on_picker_change(vid)` where `vid != 0`):
After `_show_chips(vid)`, call `_autofill_extras(vid)`.

**Vehicle deselected** (`vid == 0`):
Reset `ipva_total.value = Decimal("0")` and `empl_total.value = Decimal("0")`.

### `_autofill_extras(vid)` logic

```
1. Load Vehicle from DB → get tipo, valor_fipe
2. Open SessionLocal, read 6 business rules via RulesService
3. Compute:
   ipva = valor_fipe × ipva_pct_[tipo]   (if valor_fipe is not None, else 0)
   empl = emplacamento_valor_[tipo]
4. Set ipva_total.value = ipva
5. Set empl_total.value = empl
```

**Tipo lookup** uses a plain dict mapping tipo → rule key:
```python
PCT_BY_TIPO  = {"carro": "ipva_pct_carro",          "moto": "ipva_pct_moto",          "caminhao": "ipva_pct_caminhao"}
EMPL_BY_TIPO = {"carro": "emplacamento_valor_carro", "moto": "emplacamento_valor_moto", "caminhao": "emplacamento_valor_caminhao"}
```
Unknown tipo → both values default to 0.

### No changes to `simular()`

`simular()` already reads `ipva_total.value` and `empl_total.value` directly. Auto-filled or user-overridden values flow through unchanged.

---

## Data Migration

New file: `app/data/migrations/versions/20260528_XXXX_seed_ipva_emplacamento_rules.py`

Uses `op.execute()` with `INSERT OR IGNORE INTO business_rules (chave, valor_json, descricao, atualizado_em) VALUES (...)` for each of the 6 keys. Safe to re-run.

---

## Files to Change

| File | Change |
|---|---|
| `app/data/migrations/versions/20260528_*_seed_ipva_emplacamento_rules.py` | New: seed 6 business rule defaults |
| `app/ui/pages/configuracoes.py` | Add 6 keys to EDITABLE_KEYS, LABEL_MAP, PCT_KEYS, CURRENCY_KEYS, GROUPS |
| `app/ui/pages/simulacao.py` | Add `_autofill_extras()`, call from `_on_picker_change` |

---

## Out of Scope

- "Reset to auto" button (can be added later)
- Emplacamento defaults varying by state or year
- IPVA for vehicles with no FIPE price (field stays at 0)
