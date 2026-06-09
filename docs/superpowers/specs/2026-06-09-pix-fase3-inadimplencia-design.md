# Pix — Fase 3 (Inadimplência)

> Closes the gap FASE 1 and 2 left intentionally open: CobV charges are created today with explicit-zero `juros`/`multa` fields (Phase 1 §1b deliberate scope boundary). FASE 3 populates those fields with tenant-configurable rates drawn from `BusinessRule`, adds a real-time overdue-amount estimate to the customer portal, and adjusts `_ensure_charge` to regenerate overdue charges so they always reflect current rates.
>
> **Predecessor:** Phase 2 — Cobrança automática (`2026-06-07-02-pix-cobranca-automatica-design.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md` — "FASE 3 — Inadimplência"

## Goal

For every CobV charge covering an overdue parcela, Efí applies the tenant-configured `multa` and `juros` automatically — the customer sees the corrected amount directly in their banking app. The customer portal also shows a real-time estimate of the corrected amount (labeled as such) before they generate a PIX, so they are not surprised. No batch job, no new DB columns, no DB schema migration — the only persistence change is a seed migration adding three `BusinessRule` keys.

## In scope

### 1. New per-tenant business rules

Three new keys in `rules_service.py._RULE_DEFAULTS`, following the `inadimplencia_*` namespace:

```python
"inadimplencia_multa_pct":        (Decimal("2.00"),  "Multa por inadimplência (% sobre o valor da parcela, máx. 2% conforme BACEN)"),
"inadimplencia_juros_diario_pct": (Decimal("0.033"), "Juros diários por inadimplência (% ao dia, padrão ~1%/mês)"),
"inadimplencia_carencia_dias":    (0,                "Carência após o vencimento antes de aplicar multa e juros (dias)"),
```

**Default rationale:**
- `multa_pct = 2.00` — BACEN statutory ceiling for CDC/CCB contracts; anything above is void.
- `juros_diario_pct = 0.033` — 1%/30 days, BACEN ceiling for moratórios.
- `carencia_dias = 0` — no grace period by default; penalties start the day after `vencimento` (i.e., `dataInicio = vencimento + 1`).

**Validation in `RulesService.update` (write-time, same pattern as `pix_cobranca_automatica_dias_antes`):**
- `inadimplencia_multa_pct` ∈ [0, 2] — ceiling is statutory, not arbitrary.
- `inadimplencia_juros_diario_pct` ∈ [0, 0.1] — 3% daily would be predatory; 0.1 is a safe cap.
- `inadimplencia_carencia_dias` ∈ [0, 30].

Errors raised as `AppError` (existing convention); no silent clamping.

**Cascading edits:**
- `schemas/business_rules.py` (`BusinessRulesOut`): add `inadimplencia_multa_pct: Decimal`, `inadimplencia_juros_diario_pct: Decimal`, `inadimplencia_carencia_dias: int`.
- `api/business_rules.py` (`get_business_rules`): add the three fields to the `BusinessRulesOut` constructor call (causes a Pydantic error on GET if omitted — same risk as Phase 2 §1 noted for its new keys).
- `services/rules_service.py` (`RulesService.update`): add the three range guards.

**Seed migration `012_seed_inadimplencia_rules.py`** — mirrors `010_seed_ipva_emplacamento_rules.py` exactly:
```sql
INSERT INTO business_rules (tenant_id, chave, valor_json, descricao)
SELECT id, 'inadimplencia_multa_pct',        '2.00',  '...'
FROM tenants ON CONFLICT (tenant_id, chave) DO NOTHING;
-- same for juros_diario_pct and carencia_dias
```
Makes all three keys visible and editable in the admin business-rules UI for existing tenants immediately after migration, regardless of whether `RulesService.get_rules` has already backfilled defaults.

---

### 2. `PixProvider` Protocol — new penalty params

Phase 1 §1b hardcoded `juros`/`multa` to zero inside `EfiPixProvider` and deferred threading them through the Protocol to FASE 3. This phase makes that change:

**`pix/protocol.py` — `create_charge` new signature:**

```python
async def create_charge(
    self,
    txid: str,
    amount: Decimal,
    due_date: date,
    validity_days: int,
    description: str,
    payer: PayerInfo | None,
    multa_pct: Decimal,          # 0.00 = no penalty; 2.00 = 2% flat
    juros_diario_pct: Decimal,   # 0.00 = no interest; 0.033 = 0.033%/day
    carencia_dias: int,          # 0 = penalties start day after vencimento
) -> PixChargeData
```

**`EfiPixProvider.create_charge` mapping:**

```python
# Carência is implemented at the _ensure_charge level (see §3), not via a dataInicio field.
# The BACEN CobV spec defines multa and juros with exactly two fields: modalidade + valorPerc.
# dataInicio does not exist in the schema — passing it would be rejected or silently ignored.

# multa
if multa_pct > 0:
    body["multa"] = {
        "modalidade": 2,    # 2 = Percentual (% of original value); 1 = Valor Fixo (BRL)
        "valorPerc": str(multa_pct),
    }
else:
    body["multa"] = {"modalidade": 2, "valorPerc": "0.00"}  # explicit zero (Phase 1 §1b unchanged)

# juros
if juros_diario_pct > 0:
    body["juros"] = {
        "modalidade": 2,    # 2 = Percentual ao dia (dias corridos); 1 = Valor fixo/dia (BRL)
        "valorPerc": str(juros_diario_pct),
    }
else:
    body["juros"] = {"modalidade": 2, "valorPerc": "0.00"}
```

**`modalidade` values — verified against the official BACEN Pix openapi.yaml (authoritative spec Efí implements):**

Multa modalidades (1–2):
- `1` = Valor Fixo (fixed BRL amount)
- `2` = **Percentual** (percentage of `valor.original`) ← used here

Juros modalidades (1–8):
- `1` = Valor fixo por dia (BRL, dias corridos)
- `2` = **Percentual ao dia** (dias corridos) ← used here — matches "juros diário configurável"
- `3`–`4` = Monthly/annual percentage (calendar days)
- `5`–`8` = Same, but business days (`dias úteis`)

**Carência — implemented at `_ensure_charge` level, not via the CobV body.** The BACEN schema has no `dataInicio` field on multa or juros objects; passing it would be a schema violation. Instead, `_ensure_charge` passes zero rates when `dias_atraso <= carencia_dias` and configured rates when `dias_atraso > carencia_dias` (see §3). The daily regeneration cycle (`_created_before_today_brt`) naturally issues a new charge with real rates the first day after the grace period expires.

**`InMemoryFakePixProvider.create_charge`** — accepts all three new params, ignores them. The fake provider charges `amount` exactly. This is correct for tests: penalty math is tested via `_calculate_overdue_amount` (a pure Python function, no provider call), not by mocking PSP behavior.

---

### 3. `PixService._ensure_charge` — overdue regeneration + rate threading

`_ensure_charge` already reads `pix_validade_apos_vencimento_dias` from business rules. FASE 3 adds reading the three inadimplência rules:

```python
rules = await RulesService(self._s).get_rules(parcela.tenant_id)
multa_pct_raw    = Decimal(str(rules["inadimplencia_multa_pct"]))
juros_pct_raw    = Decimal(str(rules["inadimplencia_juros_diario_pct"]))
carencia_dias    = int(rules["inadimplencia_carencia_dias"])
validity_days    = int(rules["pix_validade_apos_vencimento_dias"])

# Carência: suppress rates while within grace period.
# dataInicio does not exist in the BACEN CobV schema, so grace period is enforced here.
dias_atraso = (date.today() - parcela.vencimento).days  # UTC server time, matches mark_overdue convention
rates_past_grace = dias_atraso > carencia_dias
multa_pct        = multa_pct_raw    if rates_past_grace else Decimal("0.00")
juros_diario_pct = juros_pct_raw    if rates_past_grace else Decimal("0.00")
```

**Overdue regeneration — new conditional before the idempotent-reuse early-return:**

```python
BRT = ZoneInfo("America/Sao_Paulo")
existing = await self._s.get(PixCharge, parcela.last_pix_charge_id) if parcela.last_pix_charge_id else None

def _created_before_today_brt(charge: PixCharge) -> bool:
    return charge.criado_em.astimezone(BRT).date() < datetime.now(BRT).date()

# Regenerate a stale overdue charge so it reflects today's accrued rates.
# Condition: overdue + rates apply today (past grace) + existing charge is from a previous day.
needs_regeneration = (
    existing is not None
    and existing.status == PixChargeStatus.pending
    and parcela.status == ParcelaPaymentStatus.overdue
    and rates_past_grace                        # only when past carência
    and _created_before_today_brt(existing)     # stops infinite regeneration loop
)
if needs_regeneration:
    await self._provider.cancel_charge(existing.txid)
    existing.status = PixChargeStatus.canceled
    self._s.add(existing)
    parcela.last_pix_charge_id = None
    existing = None
```

After this block the existing idempotent-reuse path runs normally (returns `existing` if still pending and created today, creates a new one otherwise). The new charge picks up the current rates via `provider.create_charge(..., multa_pct=multa_pct, juros_diario_pct=juros_diario_pct, carencia_dias=carencia_dias)`.

**Why daily-staleness check is required:**
Without `_created_before_today_brt`, every call to `_ensure_charge` for an overdue parcela would cancel the newly-created charge and create another — an infinite cancel-create loop across calls. The staleness check gates regeneration: a charge created today already reflects today's interest accrual and is reused by the idempotent-reuse path for the rest of the day. Tomorrow it becomes stale and is regenerated. Semantics: one regeneration per BRT calendar day per overdue parcela.

**Carência transition:** when a parcela is overdue but still within the grace period (`dias_atraso <= carencia_dias`), `rates_past_grace = False`, so the charge is generated with zero rates and `needs_regeneration = False` — same as Phase 1. The day `dias_atraso` crosses `carencia_dias`, the existing zero-rate charge is stale (created the previous day) → `needs_regeneration = True` → cancel + create with real rates. No special migration needed.

**Why BRT for the staleness check:** `PixCharge.criado_em` is UTC. Comparing against `date.today()` (server local time, UTC in prod) would mis-attribute a charge created at 22:00 BRT (01:00 UTC next day) as "tomorrow's charge." Anchoring both sides in BRT matches the business calendar, consistent with `expires_at`'s BRT-anchoring in Phase 1 §3b.

**No DB schema change.** `PixCharge` columns unchanged. The canceled charge remains in the table (audit trail). `parcela.last_pix_charge_id` is updated to point to the new charge (existing `service.py` post-creation path — no change).

---

### 4. `ParcelaService` — real-time overdue estimate

**New pure function (no DB hit, no async):**

```python
def _calculate_overdue_amount(
    valor_parcela: Decimal,
    vencimento: date,
    multa_pct: Decimal,
    juros_diario_pct: Decimal,
    carencia_dias: int,
) -> dict:
    dias_atraso = (date.today() - vencimento).days
    dias_com_encargos = max(dias_atraso - carencia_dias, 0)  # 0 on vencimento; >0 once late
    multa = (valor_parcela * multa_pct / 100).quantize(Decimal("0.01")) if dias_com_encargos > 0 else Decimal("0.00")
    juros = (valor_parcela * juros_diario_pct / 100 * dias_com_encargos).quantize(Decimal("0.01"))
    valor_corrigido = valor_parcela + multa + juros
    return {
        "valor_corrigido": valor_corrigido,
        "multa_valor": multa,
        "juros_valor": juros,
        "dias_atraso": dias_atraso,
        "estimativa": True,
    }
```

`get_schedule` and `get_parcela` both call `RulesService(self._s).get_rules(ctx.tenant_id)` once per request (already done for `validity_days` after Phase 1 lands; if not yet, add it here). For each parcela with `status == "overdue"`, attach the result of `_calculate_overdue_amount` to the response dict under key `"encargos"`:

```python
if _effective_status(p) == "overdue":
    encargos = _calculate_overdue_amount(p.valor_parcela, p.vencimento, multa_pct, juros_pct, carencia)
else:
    encargos = None
```

Response field `encargos` is `null` for non-overdue parcelas; clients must handle both.

**Real-time vs batch — explicit ruling:**

Real-time wins at this scale. `_calculate_overdue_amount` is `O(1)` arithmetic per parcela row — at most 48 rows per proposal (max contract duration), a few proposals per customer. A batch job would add a daily cron, a new DB column (`valor_corrigido` on `parcela_payments`), and a migration — all to save numbers that take microseconds to compute on read. Batch introduces stale-data risk (rules change mid-day) with no compensating benefit. Ruled out.

---

### 5. Portal frontend

**`get_schedule` response change:** Each parcela object gains an optional `encargos` field:

```typescript
interface Encargos {
  valor_corrigido: string;   // Decimal serialized as string
  multa_valor: string;
  juros_valor: string;
  dias_atraso: number;
  estimativa: true;
}

interface ParcelaItem {
  // ... existing fields ...
  encargos: Encargos | null;
}
```

**Portal parcela schedule table:** When a parcela row has `status == "overdue"` and `encargos != null`:
- Primary amount display: ~~`valor_parcela`~~ → `valor_corrigido` (with an "(estimativa)" label in muted text)
- Expandable breakdown: "Valor original: R$ X + Multa: R$ Y + Juros: R$ Z"
- Days overdue badge: "X dias em atraso"

All other statuses — unchanged.

---

## Out of scope

- **Desconto/abatimento** (early-payment discounts, renegotiation rebates) — FASE 4 territory; omitted from CobV body entirely, same as Phase 1.
- **Admin overdue portfolio view** — list of overdue parcelas per tenant, total inadimplência exposure. Deferred to a later phase.
- **Serasa/cartório/protesto integration** — not in this phase.
- **SMS/WhatsApp escalation for overdue** — later roadmap.
- **Partial payments** (`PARTIALLY_PAID` state from the pix-gpt.md state machine) — deferred; current `paid_amount` column covers the data, but the business rule for "is a partial payment acceptable?" is FASE 4.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Carência boundary: a parcela exactly at `dias_atraso == carencia_dias` gets zero-rate charge; day `carencia_dias + 1` triggers regeneration with real rates — customer may have shared the zero-rate brcode already | The zero-rate charge expires or is superseded the next day; the daily regeneration cycle means any shared brcode is at most 1 day stale. Acceptable for this use case. |
| Tenant configures `multa_pct=2.0` and `juros_diario_pct=0.033` → portal estimate and Efí's actual charge differ by a few centavos (rounding) | `estimativa: true` flag surfaced in the portal UI; label reads "estimativa". No user confusion if the expectation is set correctly. |
| Overdue-regeneration cancels a charge the customer had already shared with their spouse (who is about to pay it) | Window is single-day per regeneration (on the next `create_charge_for_parcela` call). The old brcode becomes invalid after cancel. Acceptable tradeoff — daily compounding makes a yesterday-brcode semantically stale anyway. |
| `RulesService.get_rules` called inside `_ensure_charge` (now in both `create_charge_for_parcela` and `create_auto_charge_for_parcela`) — one extra DB roundtrip per charge creation | Acceptable: charge creation is already I/O-heavy (provider network call, QR fetch, storage upload). One extra SELECT on a tiny `business_rules` table is noise. |
| `cancel_charge` fails mid-regeneration (provider error) — charge is now neither properly canceled nor re-created | `cancel_charge` errors are swallowed at the provider level (Phase 1 §cancel contract). If it fails, the old charge remains pending, `parcela.last_pix_charge_id` still points to it, and the customer uses it. Not ideal, but the alternative (partial cancellation with inconsistent state) is worse. Log the failure. |
| `inadimplencia_multa_pct > 2.0` persisted before the validation guard lands (e.g., via a direct DB edit) | `EfiPixProvider` sends whatever rate is stored; Efí will reject or cap it on their side. The statutory ceiling violation is on the operator, not the platform. |

---

## Tests

- `_calculate_overdue_amount`:
  - `carencia_dias=0`, `dias_atraso=0` (on vencimento): `dias_com_encargos=0` → multa=0, juros=0, `valor_corrigido==valor_parcela`.
  - `carencia_dias=0`, `dias_atraso=1`: `dias_com_encargos=1` → multa=`valor*multa_pct/100`, juros=`valor*juros_pct/100*1`, both non-zero.
  - `carencia_dias=3`, `dias_atraso=3`: `dias_com_encargos=0` → multa=0, juros=0 (still within grace).
  - `carencia_dias=3`, `dias_atraso=4`: `dias_com_encargos=1` → multa and 1 day juros both applied.
  - All-zero rates: `valor_corrigido==valor_parcela`, all encargo fields = `"0.00"` regardless of `dias_atraso`.
  - `dias_atraso` equals `(date.today() - vencimento).days`.

- `RulesService.update` validation:
  - `inadimplencia_multa_pct` outside `[0, 2]` → `AppError`.
  - `inadimplencia_juros_diario_pct` outside `[0, 0.1]` → `AppError`.
  - `inadimplencia_carencia_dias` outside `[0, 30]` → `AppError`.

- `PixService._ensure_charge` overdue regeneration:
  - Overdue parcela, non-zero rates, existing pending charge → old charge canceled, new charge created with correct rate params threaded to provider.
  - Overdue parcela, all-zero rates, existing pending charge → no cancel, reuse as today (rates=0 path unchanged).
  - Non-overdue parcela, existing pending charge → no cancel, reuse (unchanged path).
  - `cancel_charge` raises → old charge stays pending, no new charge created, exception logged and swallowed.
  - Overdue parcela, non-zero rates, existing pending charge created **today** (BRT) → no cancel, reuse (staleness guard prevents regeneration loop).
  - Overdue parcela, non-zero rates, existing pending charge created **yesterday** (BRT) → cancel + regenerate.

- `get_schedule` / `get_parcela` portal endpoints:
  - Overdue parcela → response includes `encargos` with correct `valor_corrigido`/`multa_valor`/`juros_valor`/`dias_atraso`/`estimativa=true`.
  - Non-overdue parcela → `encargos: null`.
  - Zero-rate tenant (all rules = 0) → `encargos` present but all amounts = `"0.00"`, `estimativa=true`.

- `BusinessRulesOut` schema: three new fields present in GET response.

- Seed migration: three rows present for existing tenants after upgrade; `downgrade` removes them.

- Protocol conformance: `InMemoryFakePixProvider.create_charge` accepts new params without error (existing fake-provider tests still pass).

---

## Acceptance checklist

- [ ] Tenant with default rates (`multa=2%, juros=0.033%/day, carência=0`) and an overdue parcela (`dias_atraso=1`): generating PIX cancels the stale zero-rate charge and creates a new one; the new CobV body has `multa={"modalidade":2,"valorPerc":"2.00"}` and `juros={"modalidade":2,"valorPerc":"0.033"}` — no `dataInicio` field (it doesn't exist in the BACEN schema).
- [ ] Overdue parcela within grace period (`dias_atraso <= carencia_dias`): charge generated with zero rates (`valorPerc="0.00"` for both); no regeneration until grace expires.
- [ ] Portal schedule for the same parcela shows `encargos.valor_corrigido > valor_parcela`, breakdown is arithmetically correct, `estimativa=true`.
- [ ] Tenant with all-zero rates: no regeneration, no encargos non-zero, existing pending charge reused.
- [ ] `inadimplencia_multa_pct=2.5` → `AppError` from `RulesService.update`; not silently accepted.
- [ ] Three new business-rule keys visible and editable in the admin business-rules UI for every tenant immediately after migration.
- [ ] `get_schedule` for a non-overdue parcela: `encargos=null`, no behavior change.
- [ ] Fake-provider integration tests pass unchanged (new Protocol params are accepted and ignored by `InMemoryFakePixProvider`).
- [ ] `carencia_dias=3`: portal shows `encargos` with zero multa/juros through day 4 of arrears (`dias_atraso <= 3`); non-zero from day 5 onward (`dias_atraso >= 4`).
- [ ] `carencia_dias=0`: portal shows zero encargos on `vencimento` itself (`dias_atraso=0`) and non-zero from `dias_atraso=1`.
