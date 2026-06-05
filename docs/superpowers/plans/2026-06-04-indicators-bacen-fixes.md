# Indicadores BACEN — Label Fixes + Derived Values Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix BACEN indicator unit bugs, change IPCA source to SGS 13522 (12m accumulated), add derived monthly/accumulated secondary values to SELIC/CDI/TX_BACEN_VEIC cards, and render human-readable unit labels in the frontend.

**Architecture:** All derived-value computation is pure math in `IndicatorsService.latest()` — no extra DB queries. Backend extends `IndicatorOut` with three nullable fields. Frontend is a thin renderer. IPCA switches from SGS 433 (monthly variation) to SGS 13522 (12m accumulated, BCB-computed directly). BrasilAPI fallback for IPCA is removed since it only serves monthly variation.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Pydantic v2 — backend. React + TypeScript / TanStack Query — frontend. Tests: pytest-asyncio + respx.

---

## File Map

| File | Change |
|---|---|
| `backend/finacialsim_saas/integrations/bacen/schema.py` | Add `pct_12m` to `Unidade` Literal |
| `backend/finacialsim_saas/integrations/bacen/sgs.py` | IPCA → SGS 13522 + `pct_12m`; TX_BACEN_VEIC → `pct_aa` |
| `backend/finacialsim_saas/integrations/bacen/brasilapi.py` | Remove `"IPCA"` from `ALIAS` |
| `backend/finacialsim_saas/schemas/indicators.py` | Add `valor_derivado`, `unidade_derivada`, `label_derivada` to `IndicatorOut` |
| `backend/finacialsim_saas/services/indicators_service.py` | Add derived-value helpers + populate in `latest()` |
| `backend/tests/test_bacen_providers.py` | Add tests for IPCA SGS 13522 + TX_BACEN_VEIC `pct_aa` + BrasilAPI IPCA removal |
| `backend/tests/test_indicators_service.py` | Add derived-value tests per indicator |
| `frontend/src/routes/admin/Indicators.tsx` | Unit label map + LABELS map + secondary value row |

---

## Task 1: Extend Unidade type and IndicatorOut schema

**Files:**
- Modify: `backend/finacialsim_saas/integrations/bacen/schema.py`
- Modify: `backend/finacialsim_saas/schemas/indicators.py`

- [ ] **Step 1: Add `pct_12m` to `Unidade`**

Open `backend/finacialsim_saas/integrations/bacen/schema.py`. Change line 8:

```python
Unidade = Literal["pct_aa", "pct_am", "pct_ad", "pct_12m"]
```

- [ ] **Step 2: Add three nullable fields to `IndicatorOut`**

Open `backend/finacialsim_saas/schemas/indicators.py`. Add to the `IndicatorOut` class after the `stale` field:

```python
class IndicatorOut(BaseModel):
    codigo: str
    valor: _DecimalAsStr
    unidade: str
    fonte: str
    data_referencia: date
    coletado_em: datetime
    stale: bool
    valor_derivado: _DecimalAsStr | None = None
    unidade_derivada: str | None = None
    label_derivada: str | None = None
```

- [ ] **Step 3: Verify no import errors**

```bash
cd backend && uv run python -c "from finacialsim_saas.schemas.indicators import IndicatorOut; from finacialsim_saas.integrations.bacen.schema import Unidade; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/finacialsim_saas/integrations/bacen/schema.py backend/finacialsim_saas/schemas/indicators.py
git commit -m "feat(indicators): extend Unidade type with pct_12m and add derived fields to IndicatorOut"
```

---

## Task 2: Fix provider sources (sgs.py + brasilapi.py)

**Files:**
- Modify: `backend/finacialsim_saas/integrations/bacen/sgs.py`
- Modify: `backend/finacialsim_saas/integrations/bacen/brasilapi.py`
- Modify: `backend/tests/test_bacen_providers.py`

- [ ] **Step 1: Write failing tests for the provider changes**

Open `backend/tests/test_bacen_providers.py`. Add these three tests at the end of the file:

```python
def test_sgs_codigos_tx_bacen_veic_unit_is_pct_aa():
    from finacialsim_saas.integrations.bacen.sgs import CODIGOS
    _, unidade = CODIGOS["TX_BACEN_VEIC"]
    assert unidade == "pct_aa"


def test_sgs_codigos_ipca_uses_series_13522():
    from finacialsim_saas.integrations.bacen.sgs import CODIGOS
    sgs_code, unidade = CODIGOS["IPCA"]
    assert sgs_code == 13522
    assert unidade == "pct_12m"


def test_brasilapi_alias_does_not_contain_ipca():
    from finacialsim_saas.integrations.bacen.brasilapi import ALIAS
    assert "IPCA" not in ALIAS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_bacen_providers.py::test_sgs_codigos_tx_bacen_veic_unit_is_pct_aa tests/test_bacen_providers.py::test_sgs_codigos_ipca_uses_series_13522 tests/test_bacen_providers.py::test_brasilapi_alias_does_not_contain_ipca -v
```

Expected: all 3 FAIL.

- [ ] **Step 3: Fix sgs.py CODIGOS**

Open `backend/finacialsim_saas/integrations/bacen/sgs.py`. Replace the `CODIGOS` dict:

```python
CODIGOS: dict[str, tuple[int, Unidade]] = {
    "SELIC": (432, "pct_aa"),
    "CDI": (12, "pct_ad"),
    "IPCA": (13522, "pct_12m"),
    "TX_BACEN_VEIC": (20714, "pct_aa"),
}
```

- [ ] **Step 4: Fix brasilapi.py — remove IPCA from ALIAS**

Open `backend/finacialsim_saas/integrations/bacen/brasilapi.py`. Replace the `ALIAS` dict:

```python
ALIAS: dict[str, tuple[str, str]] = {
    "SELIC": ("Selic", "pct_aa"),
    "CDI": ("CDI", "pct_ad"),
}
```

Remove the `"IPCA": ("IPCA", "pct_am")` entry. BrasilAPI returns monthly variation; using it as a fallback for the 12m-accumulated source would produce silently wrong data.

- [ ] **Step 5: Run new tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_bacen_providers.py::test_sgs_codigos_tx_bacen_veic_unit_is_pct_aa tests/test_bacen_providers.py::test_sgs_codigos_ipca_uses_series_13522 tests/test_bacen_providers.py::test_brasilapi_alias_does_not_contain_ipca -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Run full provider test suite to check no regressions**

```bash
cd backend && uv run pytest tests/test_bacen_providers.py -v
```

Expected: all PASS. The existing `test_chain_primary_fail_brasilapi_fallback` tests SELIC (not IPCA), so it is unaffected.

- [ ] **Step 7: Commit**

```bash
git add backend/finacialsim_saas/integrations/bacen/sgs.py backend/finacialsim_saas/integrations/bacen/brasilapi.py backend/tests/test_bacen_providers.py
git commit -m "fix(bacen): IPCA source → SGS 13522 (12m accumulated), TX_BACEN_VEIC unit → pct_aa, drop BrasilAPI IPCA fallback"
```

---

## Task 3: Implement derived values in IndicatorsService

**Files:**
- Modify: `backend/finacialsim_saas/services/indicators_service.py`
- Modify: `backend/tests/test_indicators_service.py`

The derived values are computed from the stored primary `valor` using pure math (no extra DB queries):

| Indicator | Formula | `unidade_derivada` | `label_derivada` |
|---|---|---|---|
| SELIC | `((1 + r/100)^(1/12) - 1) * 100` | `"pct_am"` | `"% a.m."` |
| CDI | `((1 + r/100)^30 - 1) * 100` | `"pct_30d"` | `"% (30d)"` |
| TX_BACEN_VEIC | `((1 + r/100)^(1/12) - 1) * 100` | `"pct_am"` | `"% a.m."` |
| IPCA | none (12m value IS the primary) | — | — |

TX_BACEN_VEIC backward-compat: existing DB rows may have `unidade = "pct_am"` until next refresh. Normalize to `"pct_aa"` at read time.

- [ ] **Step 1: Write failing tests**

Open `backend/tests/test_indicators_service.py`. Add these tests at the end:

```python
async def test_selic_latest_has_monthly_derived(session: AsyncSession):
    svc = IndicatorsService(session)
    await svc.upsert(IndicatorPoint(
        codigo="SELIC",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.50"),
        unidade="pct_aa",
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("SELIC")
    assert result is not None
    assert result.unidade == "pct_aa"
    assert result.valor_derivado is not None
    assert result.unidade_derivada == "pct_am"
    assert result.label_derivada == "% a.m."
    # 10.50% annual → ~0.835% monthly
    monthly = float(result.valor_derivado)
    assert 0.80 < monthly < 0.90


async def test_cdi_latest_has_30d_accumulated(session: AsyncSession):
    svc = IndicatorsService(session)
    await svc.upsert(IndicatorPoint(
        codigo="CDI",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("0.0521"),  # % a.d.
        unidade="pct_ad",
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("CDI")
    assert result is not None
    assert result.valor_derivado is not None
    assert result.unidade_derivada == "pct_30d"
    assert result.label_derivada == "% (30d)"
    # 0.0521% daily → ~1.57% accumulated over 30 days
    accum = float(result.valor_derivado)
    assert 1.4 < accum < 1.7


async def test_ipca_latest_has_no_derived(session: AsyncSession):
    svc = IndicatorsService(session)
    await svc.upsert(IndicatorPoint(
        codigo="IPCA",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("4.14"),
        unidade="pct_12m",
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("IPCA")
    assert result is not None
    assert result.unidade == "pct_12m"
    assert result.valor_derivado is None
    assert result.unidade_derivada is None
    assert result.label_derivada is None


async def test_tx_bacen_veic_unit_normalized_and_has_monthly_derived(session: AsyncSession):
    svc = IndicatorsService(session)
    # Insert with old (wrong) unit pct_am — simulates existing DB rows
    await svc.upsert(IndicatorPoint(
        codigo="TX_BACEN_VEIC",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("17.00"),
        unidade="pct_am",  # old wrong unit — should be normalized to pct_aa at read time
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("TX_BACEN_VEIC")
    assert result is not None
    assert result.unidade == "pct_aa"  # normalized at read time
    assert result.valor_derivado is not None
    assert result.unidade_derivada == "pct_am"
    assert result.label_derivada == "% a.m."
    # 17.00% annual → ~1.31% monthly
    monthly = float(result.valor_derivado)
    assert 1.25 < monthly < 1.40
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_indicators_service.py::test_selic_latest_has_monthly_derived tests/test_indicators_service.py::test_cdi_latest_has_30d_accumulated tests/test_indicators_service.py::test_ipca_latest_has_no_derived tests/test_indicators_service.py::test_tx_bacen_veic_unit_normalized_and_has_monthly_derived -v
```

Expected: all 4 FAIL (fields are `None`).

- [ ] **Step 3: Add math helpers and update `latest()` in indicators_service.py**

Open `backend/finacialsim_saas/services/indicators_service.py`. Add the two helper functions after the `CANONICAL_CODIGOS` line and update `latest()`:

```python
from decimal import Decimal

# --- after CANONICAL_CODIGOS ---

def _yearly_to_monthly(r: Decimal) -> Decimal:
    r_f = float(r)
    monthly = ((1 + r_f / 100) ** (1 / 12) - 1) * 100
    return Decimal(str(round(monthly, 6)))


def _daily_to_30d(r: Decimal) -> Decimal:
    r_f = float(r)
    accum = ((1 + r_f / 100) ** 30 - 1) * 100
    return Decimal(str(round(accum, 6)))


def _compute_derived(
    codigo: str, r: Decimal
) -> tuple[Decimal | None, str | None, str | None]:
    try:
        if codigo in ("SELIC", "TX_BACEN_VEIC"):
            return _yearly_to_monthly(r), "pct_am", "% a.m."
        if codigo == "CDI":
            return _daily_to_30d(r), "pct_30d", "% (30d)"
    except (ValueError, ArithmeticError, OverflowError):
        pass
    return None, None, None
```

Then update `latest()` — replace the return statement:

```python
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

        unidade = row.unidade
        if codigo == "TX_BACEN_VEIC":
            unidade = "pct_aa"

        valor_d, unidade_d, label_d = _compute_derived(codigo, Decimal(str(row.valor)))

        return IndicatorOut(
            codigo=row.codigo,
            valor=row.valor,
            unidade=unidade,
            fonte=row.fonte,
            data_referencia=row.data_referencia,
            coletado_em=coletado_em,
            stale=stale,
            valor_derivado=valor_d,
            unidade_derivada=unidade_d,
            label_derivada=label_d,
        )
```

Note: `Decimal` is already imported at the top of the file via the `IndicatorPoint` import chain. Add `from decimal import Decimal` at the top if it's not already there. Check with `grep -n "from decimal" backend/finacialsim_saas/services/indicators_service.py`.

- [ ] **Step 4: Run new tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_indicators_service.py::test_selic_latest_has_monthly_derived tests/test_indicators_service.py::test_cdi_latest_has_30d_accumulated tests/test_indicators_service.py::test_ipca_latest_has_no_derived tests/test_indicators_service.py::test_tx_bacen_veic_unit_normalized_and_has_monthly_derived -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run full indicators service test suite**

```bash
cd backend && uv run pytest tests/test_indicators_service.py tests/test_indicators_endpoints.py -v
```

Expected: all PASS. The new nullable fields are backward-compatible — existing tests don't assert `valor_derivado is None`, so they continue to pass.

- [ ] **Step 6: Commit**

```bash
git add backend/finacialsim_saas/services/indicators_service.py backend/tests/test_indicators_service.py
git commit -m "feat(indicators): compute derived values (monthly rate for SELIC/TX_BACEN_VEIC, 30d accumulated for CDI)"
```

---

## Task 4: Update Indicators.tsx (frontend)

**Files:**
- Modify: `frontend/src/routes/admin/Indicators.tsx`

The frontend receives the extended `IndicatorOut` shape. It needs to:
1. Map raw unit codes to human labels.
2. Add `TX_BACEN_VEIC` to the display labels map.
3. Render a secondary value row when `valor_derivado` is present.

- [ ] **Step 1: Update the `IndicatorOut` interface**

Open `frontend/src/routes/admin/Indicators.tsx`. Replace the `IndicatorOut` interface:

```ts
interface IndicatorOut {
  codigo: string;
  valor: string;
  unidade: string;
  fonte: string;
  data_referencia: string;
  coletado_em: string;
  stale: boolean;
  valor_derivado: string | null;
  unidade_derivada: string | null;
  label_derivada: string | null;
}
```

- [ ] **Step 2: Add UNIT_LABELS map and update LABELS map**

Replace the existing `LABELS` const and add `UNIT_LABELS` directly below it:

```ts
const LABELS: Record<string, string> = {
  SELIC: "SELIC",
  CDI: "CDI",
  IPCA: "IPCA",
  TX_BACEN_VEIC: "Taxa BACEN Veíc.",
};

const UNIT_LABELS: Record<string, string> = {
  pct_aa:  "% a.a.",
  pct_am:  "% a.m.",
  pct_ad:  "% a.d.",
  pct_12m: "% (12m)",
  pct_30d: "% (30d)",
};
```

- [ ] **Step 3: Update the card render to use labels and secondary value**

Find the card JSX block inside the `.map()`. Replace it with:

```tsx
<div key={ind.codigo} className="bg-[#0F172A] border border-[#1E293B] rounded-lg p-5">
  <p className="text-xs text-[#64748B] uppercase tracking-wider">
    {LABELS[ind.codigo] ?? ind.codigo}
  </p>
  <p className="text-2xl font-semibold text-[#F8FAFC] mt-1">
    {ind.valor}
    <span className="text-sm text-[#64748B] ml-1">
      {UNIT_LABELS[ind.unidade] ?? ind.unidade}
    </span>
  </p>
  {ind.valor_derivado && (
    <p className="text-sm text-[#64748B] mt-0.5">
      {ind.valor_derivado}
      <span className="ml-1">{ind.label_derivada}</span>
    </p>
  )}
  <p className="text-xs text-[#475569] mt-2">{ind.data_referencia}</p>
</div>
```

Note: the old code used `ind.data` — the actual field is `data_referencia`. If the existing code already uses `ind.data`, check the field name returned by the API and match it. The backend returns `data_referencia`.

- [ ] **Step 4: Run frontend type check**

```bash
cd frontend && npm run build 2>&1 | head -40
```

Expected: no TypeScript errors related to `Indicators.tsx`. Fix any type errors before proceeding.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/admin/Indicators.tsx
git commit -m "feat(frontend): unit labels, TX_BACEN_VEIC display name, secondary value row on indicator cards"
```

---

## Task 5: Full regression run

- [ ] **Step 1: Run all backend indicator-related tests**

```bash
cd backend && uv run pytest tests/test_bacen_providers.py tests/test_indicators_service.py tests/test_indicators_endpoints.py tests/test_arq_jobs.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run full backend test suite**

```bash
cd backend && uv run pytest -x -q
```

Expected: all PASS (or pre-existing failures only — do not introduce new failures).

- [ ] **Step 3: Run frontend lint + type check**

```bash
cd frontend && npm run build
```

Expected: clean build, no errors.

- [ ] **Step 4: Verify in browser (optional but recommended)**

Start the dev stack (`./dev.sh` or equivalent). Navigate to Admin → Indicadores. After clicking "Atualizar agora" and waiting for a refresh:
- SELIC card: shows `% a.a.` primary, `% a.m.` secondary
- CDI card: shows `% a.d.` primary, `% (30d)` secondary
- IPCA card: shows value with `% (12m)` label, no secondary line
- TX_BACEN_VEIC card: shows `% a.a.` primary, `% a.m.` secondary, label "Taxa BACEN Veíc."
