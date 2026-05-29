# Design Spec — Simulacao Smart Defaults

**Date:** 2026-05-26
**Status:** Approved
**File scope:** `app/ui/pages/simulacao.py` only

---

## Overview

Three UX improvements to the Simulacao form:

1. **Cliente selector** — searchable dropdown to associate a client with the simulation.
2. **Entrada smart default** — pre-filled from `entrada_minima_pct x valor_veiculo`; live % indicator with amber warning when below minimum.
3. **Taxa mensal from BACEN** — pre-filled from `TX_BACEN_VEIC` indicator; auto-updates reactively while the page is open.

No new models, no migrations, no new services.

---

## Data Loading

At the start of `content()`, before any UI is built, one synchronous DB session reads all page data:

```python
with SessionLocal() as session:
    entrada_minima_pct = Decimal(
        RulesService(session).get_raw("entrada_minima_pct") or "0.10"
    )
    taxa_bacen_row = IndicatorRepository(session).get_latest("TX_BACEN_VEIC")
    taxa_bacen_val = taxa_bacen_row.valor if taxa_bacen_row else None
    clients = ClientService(session).find("")
```

Session closes immediately. All subsequent DB access (simular, nova_a_partir, etc.) uses existing per-callback session patterns unchanged.

**New imports to add to `simulacao.py`:**

- `from app.data.repositories import IndicatorRepository`
- `from app.services.client_service import ClientService`
- `from app.services.rules_service import RulesService`

---

## Feature 1: Cliente Selector

### Placement

Top of the left form column, above the existing "Veiculo" section label.

### Section label

```text
"Cliente"  — styled: text-xs font-semibold text-slate-500 uppercase tracking-widest
```

### Widget

```python
cliente_options = {0: "— sem cliente —"}
cliente_options.update({c.id: f"{c.nome}  ({c.cpf_cnpj})" for c in clients})

cliente_sel = ui.select(
    cliente_options,
    value=0,
    label="Cliente",
    with_input=True,
).classes("w-full")
```

- `with_input=True` enables built-in client-side search filter.
- Sentinel `0` (int) used for "no client" — matches the vehicle picker pattern. `None` keys cause JSON serialization issues with Quasar's QSelect.
- No `clearable` needed — user selects `0` ("— sem cliente —") to deselect.

### DTO wiring

```python
cliente_id = cliente_sel.value if cliente_sel.value != 0 else None
```

`SimulationInputDTO.cliente_id` is already `int | None`. No service-layer changes needed.

### Loaded-simulation restore

When a simulation is loaded from `/veiculos`, add `"cliente_id": _sim.cliente_id` to the `_loaded_sim["sim"]` dict. In the pre-fill block, set `cliente_sel.value = _d["cliente_id"] or 0`.

### nova_a_partir

`nova_a_partir()` leaves the form values intact — `cliente_sel` keeps the restored client. No change needed.

---

## Feature 2: Entrada Pre-fill + % Indicator

### Pre-fill

`valor_entrada` is initialized at page load to:

```text
entrada_default = quantize_brl(entrada_minima_pct * valor_veiculo.default)
```

This replaces the current hardcoded `Decimal("10000")` default.

### % Indicator label

A `ui.label` placed directly below the `valor_entrada` input:

```text
"12.5%  (min. 10%)"
```

**Color logic:**

| Condition | CSS class |
| ----------- | ----------- |
| current % >= `entrada_minima_pct` | `text-slate-400` |
| current % < `entrada_minima_pct` | `text-amber-500` |
| `valor_veiculo` is zero | label hidden |

**Update trigger:** `CurrencyInput` fires `on_change` on `blur` (click-away). After `_update_pct_label` is defined, bind it to both fields via `valor_veiculo.input.on("blur", ...)` and `valor_entrada.input.on("blur", ...)`. Call it once immediately at page render to show the initial state.

**Chip-click recalculation:** An `entrada_modified = {"v": False}` flag tracks manual edits. `_set_valor_veiculo` (chip click) recalculates `valor_entrada = quantize_brl(entrada_minima_pct * new_val)` and calls `_update_pct_label()` only when `not entrada_modified["v"]`. `valor_entrada.input.on("blur", lambda _: entrada_modified.__setitem__("v", True))` sets the flag when the user manually edits the field.

### Behavior after user edits

Once the user manually touches `valor_entrada` (blur fires, `entrada_modified = True`), subsequent chip clicks no longer recalculate it. The % indicator still updates on every blur of either field.

---

## Feature 3: Taxa Mensal — BACEN Pre-fill + Live Update

### Pre-fill

```python
taxa_initial = taxa_bacen_val if taxa_bacen_val is not None else Decimal("0")
taxa = PercentInput("Taxa mensal", taxa_initial)
```

### BACEN hint label

A `ui.label` directly below `taxa`, styled `text-xs italic`:

| State | Text | Color |
|-------|------|-------|
| Data loaded | `"BACEN TX_VEIC: 1.89% a.m."` | `text-slate-400` |
| No data | `"sem dados BACEN — informe manualmente"` | `text-amber-500` |

The hint reflects the DB value, not the current input value.

### Live update (reactive polling)

```python
taxa_modified = {"v": False}

def _on_taxa_change():
    taxa_modified["v"] = True

def _poll_bacen():
    with SessionLocal() as session:
        row = IndicatorRepository(session).get_latest("TX_BACEN_VEIC")
        new_val: Decimal | None = row.valor if row else None
    if new_val is None:
        return
    bacen_hint.set_text(f"BACEN TX_VEIC: {new_val * 100:.2f}% a.m.")
    bacen_hint.classes("text-slate-400", replace=True)
    bacen_hint.update()
    if not taxa_modified["v"]:
        taxa.value = new_val
        taxa.update()

ui.timer(60, _poll_bacen)
```

**State transitions:**

```text
page opens, no data  ->  taxa=0.00%, hint=amber "sem dados BACEN — informe manualmente"
timer fires, data arrives  ->  taxa=1.89% (auto), hint=gray "BACEN TX_VEIC: 1.89% a.m."
user edits taxa manually  ->  taxa=user value, taxa_modified=True; hint still updates on poll
subsequent polls  ->  taxa unchanged (flag set), hint refreshes with latest BACEN value
```

---

## Files Changed

| File | Change |
|------|--------|
| `app/ui/pages/simulacao.py` | Add 3 imports; read page data in `content()`; add cliente selector, entrada default + % label, taxa default + hint + timer |

No other files are modified.

---

## Out of Scope

- Persisting `cliente_id` into the proposal/PDF (future work).
- Displaying client details (phone, email, renda) after selection.
- Filtering the client list by type (PF/PJ).
- Debounced server-side client search (not needed at current scale).
