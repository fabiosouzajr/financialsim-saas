# Indicadores BACEN — Label Fixes + Derived Values — Design Spec

**Date:** 2026-06-04  
**Status:** Approved (revised after grill session)

## Problem

The Indicadores BACEN admin panel has several display and correctness issues:

1. Unit strings (`pct_am`, `pct_aa`) are shown raw instead of human-readable labels.
2. `TX_BACEN_VEIC` is stored with unit `pct_am` but is actually an annual rate (`pct_aa`) from SGS 20714.
3. SELIC and TX_BACEN_VEIC show only the yearly rate — users need the monthly equivalent.
4. CDI shows only the daily rate — users need the 30-day accumulated.
5. IPCA shows the latest monthly variation — users need the 12-month accumulated.
6. `TX_BACEN_VEIC` has no display label in the `LABELS` map.

## Scope

- Backend: unit bug fix + source change for IPCA + derived-value math in `indicators_service.py` + optional schema fields + `Unidade` type extension.
- Frontend: unit label mapping + secondary value row on indicator cards + `LABELS` map addition.
- No new endpoints, no migrations, no new tables.
- No series DB queries introduced — all derived values use pure math on the stored primary value.

## Architecture

All derived-value computation happens in the backend service layer. The frontend is a thin renderer. No extra DB queries: derived values are computed inline in `IndicatorsService.latest()` from the stored `valor`.

## Backend Changes

### 1. Fix TX_BACEN_VEIC unit (`sgs.py`)

Change `CODIGOS["TX_BACEN_VEIC"]` unit from `"pct_am"` to `"pct_aa"`:

```python
"TX_BACEN_VEIC": (20714, "pct_aa"),
```

### 2. Change IPCA source to SGS 13522 (`sgs.py`)

SGS 433 returns monthly variation. SGS 13522 returns the 12-month accumulated IPCA directly (BCB-computed). Replace:

```python
# Before
"IPCA": (433, "pct_am"),
# After
"IPCA": (13522, "pct_12m"),
```

### 3. Remove IPCA from BrasilAPI fallback (`brasilapi.py`)

BrasilAPI's `/taxas/v1/IPCA` returns the monthly variation (`pct_am`), not the 12m accumulated. Keeping it as a fallback would silently display wrong data. Remove `"IPCA"` from the `ALIAS` dict. IPCA updates monthly; a temporary SGS outage is acceptable.

### 4. Extend `Unidade` type (`integrations/bacen/schema.py`)

```python
Unidade = Literal["pct_aa", "pct_am", "pct_ad", "pct_12m"]
```

### 5. Extend `IndicatorOut` schema (`schemas/indicators.py`)

Add three optional fields:

```python
valor_derivado: _DecimalAsStr | None = None
unidade_derivada: str | None = None
label_derivada: str | None = None
```

### 6. Compute derived values + normalize TX_BACEN_VEIC (`services/indicators_service.py`)

`IndicatorsService.latest()` populates derived fields and normalizes the TX_BACEN_VEIC unit at read time:

| Indicator | Primary unit | Derived formula | `unidade_derivada` | `label_derivada` |
|---|---|---|---|---|
| SELIC | `pct_aa` | `((1 + r/100)^(1/12) - 1) * 100` | `pct_am` | `"% a.m."` |
| CDI | `pct_ad` | `((1 + r/100)^30 - 1) * 100` | `pct_30d` | `"% (30d)"` |
| IPCA | `pct_12m` | none | — | — |
| TX_BACEN_VEIC | `pct_aa` | `((1 + r/100)^(1/12) - 1) * 100` | `pct_am` | `"% a.m."` |

TX_BACEN_VEIC backward compat: existing DB rows have `pct_am` until next refresh. Normalize at read time — if `row.codigo == "TX_BACEN_VEIC"`, override `unidade` to `"pct_aa"` regardless of stored value.

CDI approximation rationale: CDI daily rate changes only on COPOM meeting days (~8×/year). Compounding the single stored rate over 30 days is indistinguishable from compounding 30 actual daily values in practice.

## Frontend Changes

### 7. Unit label map (`Indicators.tsx`)

```ts
const UNIT_LABELS: Record<string, string> = {
  pct_aa:  "% a.a.",
  pct_am:  "% a.m.",
  pct_ad:  "% a.d.",
  pct_12m: "% (12m)",
  pct_30d: "% (30d)",
};
```

Replace `ind.unidade` render with `UNIT_LABELS[ind.unidade] ?? ind.unidade`. Same map applies to `ind.unidade_derivada`.

### 8. Add TX_BACEN_VEIC to LABELS map (`Indicators.tsx`)

```ts
const LABELS: Record<string, string> = {
  SELIC:        "SELIC",
  CDI:          "CDI",
  IPCA:         "IPCA",
  TX_BACEN_VEIC: "Taxa BACEN Veíc.",
};
```

### 9. Secondary value row on indicator cards (`Indicators.tsx`)

When `ind.valor_derivado` is present, render a second line below the primary value:

```
┌─────────────────────────┐
│ SELIC                   │
│ 10.50   % a.a.          │  ← primary (existing style)
│  0.84   % a.m.          │  ← derived: text-sm, text-[#64748B], label from label_derivada
│ 2026-06-04              │
└─────────────────────────┘
```

## Error Handling

- If derivation produces a non-finite result (e.g. `valor` is zero or negative), set `valor_derivado = None` — card shows primary only.
- If series data is unavailable (IPCA, no derivation needed), the card shows the primary 12m value directly.
- The `_to_decimal_str` normalizer handles `Decimal` rounding, keeping at least 2 decimal places.

## Testing

- Unit test `IndicatorsService.latest()` for each indicator: verify `valor_derivado`, `unidade_derivada`, `label_derivada` values.
- Assert `TX_BACEN_VEIC` unit is normalized to `pct_aa` even when DB row has `pct_am`.
- Assert IPCA `latest()` returns no `valor_derivado`.
- Assert `TX_BACEN_VEIC` unit is `pct_aa` in `sgs.py` CODIGOS.
- Assert `"IPCA"` is absent from `brasilapi.py` ALIAS.
- Existing indicator endpoint tests continue to pass (new fields are optional/nullable).
