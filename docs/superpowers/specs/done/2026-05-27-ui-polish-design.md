# Design Spec — UI Polish: Login, Cadastro, Simulação, Configurações

**Date:** 2026-05-27
**Status:** approved — grill complete 2026-05-27
**Design system ref:** `design-system/financialsim/MASTER.md`

---

## Scope

Four targeted UI improvement areas. All changes are surgical — no architectural changes,
no new routes, no new services. Each area is independent.

---

## 1. Login Page (`app/ui/pages/login.py`)

### 1.1 Field sizing

`user_select` currently has no width class, making it narrower than the PIN input on some
viewports. Add `.classes("w-full")` to `user_select` to match PIN and button width.

### 1.2 Keyboard navigation

Bind Enter key on the PIN input to trigger `do_login()`. NiceGUI supports
`input.on("keydown.enter", callback)`. Also bind Enter on the `user_select` so
keyboard-only users can tab through and submit.

```
pin_input.on("keydown.enter", lambda _: do_login())
```

Only `pin_input` gets the Enter binding. **Do not bind Enter on `user_select`** — Quasar's q-select
intercepts Enter internally to confirm dropdown selection, making an outer binding fragile.

**No other changes** to the login page layout or logic.

---

## 2. Cadastro Page (`app/ui/pages/cadastro.py`)

### 2.1 Reduce padding

Change the outer split row from `gap-6` → `gap-4` (saves ~8px of horizontal gap,
consistent with the `--space-md` token from the design system).

### 2.2 Client table — center-aligned headers, hide unnecessary columns

Remove `tipo` and `telefone` columns from the `columns` list. Keep only:
- `nome` — "Nome"
- `doc` — "CPF/CNPJ"

Add `"align": "center"` to every column definition — this centers both the header label
and the cell content. Also remove `tipo` and `telefone` from the row dict built in
`_refresh()`.

**Result:** a narrower, cleaner table that fits comfortably alongside the form.

---

## 3. Simulação Page — Charts and KPI size

### 3.1 Chart heights (`app/ui/components/charts.py`)

| Chart | Current height | New height |
|---|---|---|
| `composition_chart` | 320 | 240 |
| `saldo_devedor_chart` | 300 | 220 |
| `parcela_total_chart` | 260 | 200 |

All `margin` values stay the same.

### 3.2 Compact KPI cards (`app/ui/theme.py`)

Tighten `.kpi-card-compact` and `.kpi-value-compact`:

| Property | Current | New |
|---|---|---|
| `.kpi-card-compact` padding | `0.5rem 0.75rem` | `0.375rem 0.625rem` |
| `.kpi-value-compact` font-size | `1.1rem` | `0.95rem` |

The `kpi-label` size and `kpi-group-label` are unchanged — they are already compact.

---

## 4. Configurações — Regras de Negócio (`app/ui/pages/configuracoes.py`)

This is the most involved section. Three sub-problems: labels, percent inputs, grouping.

### 4.1 Human-readable label map

Replace raw key names with a `LABEL_MAP` dict in `configuracoes.py`:

```python
LABEL_MAP = {
    "entrada_minima_pct":               "Entrada mínima",
    "prazo_minimo_meses":               "Prazo mínimo (meses)",
    "prazo_maximo_meses":               "Prazo máximo (meses)",
    "taxa_minima_mes":                  "Taxa mínima ao mês",
    "taxa_maxima_mes":                  "Taxa máxima ao mês",
    "dias_max_carencia":                "Carência máxima (dias)",
    "valor_minimo_financiado":          "Valor mínimo financiado (R$)",
    "incluir_iof_default":              "Incluir IOF por padrão",
    "iof_fixo_pct":                     "IOF fixo",
    "iof_diario_pct":                   "IOF diário",
    "iof_diario_max_dias":              "IOF diário — máx. dias",
    "rateio_ipva_meses_default":        "Rateio IPVA (meses padrão)",
    "rateio_emplacamento_meses_default":"Rateio emplacamento (meses padrão)",
    "backup_diario_horario":            "Horário do backup diário",
    "update_indicadores_horario":       "Horário de atualização de indicadores",
    "fipe_cache_listas_ttl_dias":       "Cache FIPE — listas (dias)",
    "fipe_cache_preco_ttl_horas":       "Cache FIPE — preço (horas)",
}
```

### 4.2 Input types per key

Keys fall into four categories, each using a different widget:

| Category | Keys | Widget |
|---|---|---|
| **Percent** | `entrada_minima_pct`, `taxa_minima_mes`, `taxa_maxima_mes`, `iof_fixo_pct`, `iof_diario_pct` | `PercentInput` (existing component) |
| **Boolean** | `incluir_iof_default` | `ui.switch` |
| **Integer** | `prazo_minimo_meses`, `prazo_maximo_meses`, `dias_max_carencia`, `iof_diario_max_dias`, `rateio_ipva_meses_default`, `rateio_emplacamento_meses_default`, `fipe_cache_listas_ttl_dias`, `fipe_cache_preco_ttl_horas` | `ui.number` (format=`int`) |
| **Currency** | `valor_minimo_financiado` | `CurrencyInput` (existing component) |
| **String** | `backup_diario_horario`, `update_indicadores_horario` | `ui.input` |

**Percent widget:** `PercentInput` from `app/ui/components/percent_input.py` — user types
`20`, it displays `20,00%`, `.value` property returns `Decimal("0.20")`. Initialize with
`Decimal(raw or "0")` from `svc.get_raw(k)`. On save: `str(pct_inp.value)`.

**Boolean widget:** `ui.switch(label)` — initialize with
`raw.lower() in ("true", "1", "yes")`. On save: `"true"` if checked else `"false"`.

**Integer widget:** `ui.number(label, value=int(raw or 0), format="%d")`.
On save: `str(int(num_inp.value or 0))`.

**Currency widget:** `CurrencyInput(label, Decimal(raw or "0"))` from
`app/ui/components/currency_input.py`. On save: `str(currency_inp.value)`.

**String widget:** `ui.input(label, value=raw)` — unchanged from today.

**Safe initialization:** all widget initializations must wrap the `raw` parse in a
silent fallback — a corrupted DB value must not crash the page:

```python
def _safe_decimal(raw: str) -> Decimal:
    try: return Decimal(raw or "0")
    except Exception: return Decimal("0")

def _safe_int(raw: str) -> int:
    try: return int(raw or 0)
    except Exception: return 0
```

Use `_safe_decimal` for Percent and Currency widgets, `_safe_int` for Integer widgets.

### 4.3 Grouping

Replace the flat key loop with four `ui.expansion` sections (all open by default):

| Group | Keys |
|---|---|
| **Financiamento** | `entrada_minima_pct`, `prazo_minimo_meses`, `prazo_maximo_meses`, `taxa_minima_mes`, `taxa_maxima_mes`, `dias_max_carencia`, `valor_minimo_financiado` |
| **IOF** | `incluir_iof_default`, `iof_fixo_pct`, `iof_diario_pct`, `iof_diario_max_dias` |
| **Extras / Rateio** | `rateio_ipva_meses_default`, `rateio_emplacamento_meses_default` |
| **Sistema** | `backup_diario_horario`, `update_indicadores_horario`, `fipe_cache_listas_ttl_dias`, `fipe_cache_preco_ttl_horas` |

Each group renders as `ui.expansion(group_title, value=<open>)` wrapping a
`ui.column().classes("gap-3 px-1")` with the group's widgets inside.

**Default open/closed state:**

| Group | Default |
|---|---|
| Financiamento | open (`value=True`) |
| IOF | open (`value=True`) |
| Extras / Rateio | collapsed (`value=False`) |
| Sistema | collapsed (`value=False`) |

The "Salvar tudo" button stays below all groups, full-width.

### 4.4 Save logic

Replace the current `for k, inp in inputs.items()` loop with a unified save that
handles each widget type. Use three sets defined alongside `LABEL_MAP`:

```python
PCT_KEYS  = {"entrada_minima_pct", "taxa_minima_mes", "taxa_maxima_mes",
             "iof_fixo_pct", "iof_diario_pct"}
BOOL_KEYS = {"incluir_iof_default"}
INT_KEYS  = {"prazo_minimo_meses", "prazo_maximo_meses", "dias_max_carencia",
             "iof_diario_max_dias", "rateio_ipva_meses_default",
             "rateio_emplacamento_meses_default",
             "fipe_cache_listas_ttl_dias", "fipe_cache_preco_ttl_horas"}
# remaining keys fall through to plain string save
```

Save loop:

```python
for key, widget in widgets.items():
    if key in PCT_KEYS:
        value = str(widget.value)                   # Decimal fraction
    elif key in BOOL_KEYS:
        value = "true" if widget.value else "false"
    elif key in INT_KEYS:
        value = str(int(widget.value or 0))
    else:
        value = widget.value or ""
    svc.set(key, value, user_id=user_id)
```

`EDITABLE_KEYS` list at top of file stays as the single source of truth for which
keys are managed.

---

## Design system compliance notes

- Spacing tokens applied: `gap-4` (md), `gap-3` (sm), `px-1` padding inside groups.
- IBM Plex Sans already in use globally — no change.
- Dark mode OLED theme (MASTER.md) represents the project's future direction;
  this changeset does **not** migrate the color palette — that is a separate task.
- Focus states: NiceGUI/Quasar default focus ring meets WCAG 2.1 AA.
  The Enter-key binding adds a keyboard path without removing mouse paths.

---

## Files changed

| File | Change |
|---|---|
| `app/ui/pages/login.py` | `w-full` on select, Enter key bindings |
| `app/ui/pages/cadastro.py` | `gap-4`, remove 2 columns, add `align:center` |
| `app/ui/components/charts.py` | Reduce 3 chart heights |
| `app/ui/theme.py` | Tighten `.kpi-card-compact` padding + font-size |
| `app/ui/pages/configuracoes.py` | `LABEL_MAP`, widget types (pct/bool/int/currency/str), grouping, safe init, save logic |

No new files. No new dependencies. No schema changes.
