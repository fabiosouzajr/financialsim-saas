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
# dataInicio: penalties start the day AFTER vencimento + carencia_dias
# (carencia_dias=0 → day after vencimento; carencia_dias=3 → 4 days after vencimento)
penalty_start = (due_date + timedelta(days=carencia_dias + 1)).isoformat()

# multa
if multa_pct > 0:
    body["multa"] = {
        "modalidade": 2,            # 2 = percentage of original value
        "valorPerc": str(multa_pct),
        "dataInicio": penalty_start,
    }
else:
    body["multa"] = {"modalidade": 2, "valorPerc": "0.00"}  # explicit zero (Phase 1 §1b unchanged)

# juros
if juros_diario_pct > 0:
    body["juros"] = {
        "modalidade": 1,               # 1 = daily simple interest (valorPerc = % per day)
        "valorPerc": str(juros_diario_pct),
        "dataInicio": penalty_start,
    }
else:
    body["juros"] = {"modalidade": 1, "valorPerc": "0.00"}
```

`modalidade` values (verified against the Efí SDK's `pix_create_due_charge.py` example — same verification rigor Phase 1 applied to distinguishing `pix_create_charge` from `pix_create_due_charge`):
- Multa modalidade `2` — percentage (`valorPerc`); modalidade `1` is a fixed `valor` in BRL. We use percentage because the business rules store a rate, not a fixed amount per parcela.
- Juros modalidade `1` — daily rate (`valorPerc` = % per day); Efí accrues against the original value across the number of days elapsed since `dataInicio`. Other modalidades (monthly, etc.) exist — daily was chosen to match the "juros diário configurável" requirement literally.

`dataInicio` semantics: `carencia_dias=0` → `penalty_start = vencimento + 1` (the day after vencimento — a customer paying exactly on the due date is never penalized). `carencia_dias=3` → penalties start 4 days after vencimento. **Verify sandbox behavior** — confirm a payment on `penalty_start - 1` does not apply charges, and one on `penalty_start` does, before enabling non-zero rates on a live tenant.

**`InMemoryFakePixProvider.create_charge`** — accepts all three new params, ignores them. The fake provider charges `amount` exactly. This is correct for tests: penalty math is tested via `_calculate_overdue_amount` (a pure Python function, no provider call), not by mocking PSP behavior.

---

### 3. `PixService._ensure_charge` — overdue regeneration + rate threading

`_ensure_charge` already reads `pix_validade_apos_vencimento_dias` from business rules. FASE 3 adds reading the three inadimplência rules:

```python
rules = await RulesService(self._s).get_rules(parcela.tenant_id)
multa_pct        = Decimal(str(rules["inadimplencia_multa_pct"]))
juros_diario_pct = Decimal(str(rules["inadimplencia_juros_diario_pct"]))
carencia_dias    = int(rules["inadimplencia_carencia_dias"])
validity_days    = int(rules["pix_validade_apos_vencimento_dias"])
```

**Overdue regeneration — new conditional before the idempotent-reuse early-return:**

```python
existing = await self._s.get(PixCharge, parcela.last_pix_charge_id) if parcela.last_pix_charge_id else None
rates_configured = multa_pct > 0 or juros_diario_pct > 0

if (
    existing is not None
    and existing.status == PixChargeStatus.pending
    and parcela.status == ParcelaPaymentStatus.overdue
    and rates_configured
):
    # cancel the zero-rate charge and fall through to create a new one with real rates
    await self._provider.cancel_charge(existing.txid)
    existing.status = PixChargeStatus.canceled
    self._s.add(existing)
    parcela.last_pix_charge_id = None
    existing = None
```

After this block the existing idempotent-reuse path runs normally (returns `existing` if still pending, creates a new one otherwise). The new charge picks up the current rates via `provider.create_charge(..., multa_pct=multa_pct, ...)`.

**Why always-regenerate for overdue + non-zero rates:**
- A CobV charge's juros/multa are baked in at creation time (Efí can't update them on an existing charge). A charge created yesterday with zero rates will never apply penalties, regardless of what the tenant configures today.
- Daily interest compounds — a charge created on day 5 of arrears will compute fewer days of interest than one created on day 6. Regenerating ensures the brcode always reflects the current accrual.
- Cancel-then-create is idempotent across repeated calls (same parcela, same overdue status, rates unchanged → only the first call cancels; subsequent calls create a fresh one which is then returned via the idempotent-reuse path on the next call). Actually: since each regeneration creates a NEW `PixCharge` row (new `txid`), subsequent same-day calls will hit the reuse path on the new charge and return it unchanged. The one-cancel-per-day cadence is only broken if the customer generates two charges in less than a day — acceptable.

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
    dias_com_encargos = max(dias_atraso - carencia_dias - 1, 0)  # +1: no penalty on vencimento itself
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
| `dataInicio` semantics on Efí: "starts on" vs "starts the day after" `due_date + carencia_dias` | Explicit sandbox smoke-test: create a CobV with `carencia_dias=1`, pay it on `vencimento+1`, verify whether multa applies. Document expected behavior in the runbook. |
| Tenant configures `multa_pct=2.0` and `juros_diario_pct=0.033` → portal estimate and Efí's actual charge differ by a few centavos (rounding) | `estimativa: true` flag surfaced in the portal UI; label reads "estimativa". No user confusion if the expectation is set correctly. |
| Overdue-regeneration cancels a charge the customer had already shared with their spouse (who is about to pay it) | Window is single-day per regeneration (on the next `create_charge_for_parcela` call). The old brcode becomes invalid after cancel. Acceptable tradeoff — daily compounding makes a yesterday-brcode semantically stale anyway. |
| `RulesService.get_rules` called inside `_ensure_charge` (now in both `create_charge_for_parcela` and `create_auto_charge_for_parcela`) — one extra DB roundtrip per charge creation | Acceptable: charge creation is already I/O-heavy (provider network call, QR fetch, storage upload). One extra SELECT on a tiny `business_rules` table is noise. |
| `cancel_charge` fails mid-regeneration (provider error) — charge is now neither properly canceled nor re-created | `cancel_charge` errors are swallowed at the provider level (Phase 1 §cancel contract). If it fails, the old charge remains pending, `parcela.last_pix_charge_id` still points to it, and the customer uses it. Not ideal, but the alternative (partial cancellation with inconsistent state) is worse. Log the failure. |
| `inadimplencia_multa_pct > 2.0` persisted before the validation guard lands (e.g., via a direct DB edit) | `EfiPixProvider` sends whatever rate is stored; Efí will reject or cap it on their side. The statutory ceiling violation is on the operator, not the platform. |

---

## Tests

- `_calculate_overdue_amount`:
  - Zero carência, day 1: multa + 1 day juros.
  - `carencia_dias=3`, day 2: no multa, no juros (within grace).
  - `carencia_dias=3`, day 4: multa + 1 day juros.
  - All-zero rates: `valor_corrigido == valor_parcela`, both encargo fields = `"0.00"`.
  - `dias_atraso` correct (today − vencimento).

- `RulesService.update` validation:
  - `inadimplencia_multa_pct` outside `[0, 2]` → `AppError`.
  - `inadimplencia_juros_diario_pct` outside `[0, 0.1]` → `AppError`.
  - `inadimplencia_carencia_dias` outside `[0, 30]` → `AppError`.

- `PixService._ensure_charge` overdue regeneration:
  - Overdue parcela, non-zero rates, existing pending charge → old charge canceled, new charge created with correct rate params threaded to provider.
  - Overdue parcela, all-zero rates, existing pending charge → no cancel, reuse as today (rates=0 path unchanged).
  - Non-overdue parcela, existing pending charge → no cancel, reuse (unchanged path).
  - `cancel_charge` raises → old charge stays pending, no new charge created, exception logged and swallowed.

- `get_schedule` / `get_parcela` portal endpoints:
  - Overdue parcela → response includes `encargos` with correct `valor_corrigido`/`multa_valor`/`juros_valor`/`dias_atraso`/`estimativa=true`.
  - Non-overdue parcela → `encargos: null`.
  - Zero-rate tenant (all rules = 0) → `encargos` present but all amounts = `"0.00"`, `estimativa=true`.

- `BusinessRulesOut` schema: three new fields present in GET response.

- Seed migration: three rows present for existing tenants after upgrade; `downgrade` removes them.

- Protocol conformance: `InMemoryFakePixProvider.create_charge` accepts new params without error (existing fake-provider tests still pass).

---

## Acceptance checklist

- [ ] Tenant with default rates (`multa=2%, juros=0.033%/day, carência=0`) and an overdue parcela: generating PIX cancels the old zero-rate charge and creates a new one; the new CobV body has `multa.modalidade=2`/`multa.valorPerc="2.00"` and `juros.modalidade=1`/`juros.valorPerc="0.033"` with `dataInicio = vencimento`.
- [ ] Portal schedule for the same parcela shows `encargos.valor_corrigido > valor_parcela`, breakdown is arithmetically correct, `estimativa=true`.
- [ ] Tenant with all-zero rates: no regeneration, no encargos non-zero, existing pending charge reused.
- [ ] `inadimplencia_multa_pct=2.5` → `AppError` from `RulesService.update`; not silently accepted.
- [ ] Three new business-rule keys visible and editable in the admin business-rules UI for every tenant immediately after migration.
- [ ] `get_schedule` for a non-overdue parcela: `encargos=null`, no behavior change.
- [ ] Fake-provider integration tests pass unchanged (new Protocol params are accepted and ignored by `InMemoryFakePixProvider`).
- [ ] `carencia_dias=3`: portal shows `encargos` with zero multa/juros through day 4 of arrears (`dias_atraso <= 3`); non-zero from day 5 onward (`dias_atraso >= 4`).
- [ ] `carencia_dias=0`: portal shows zero encargos on `vencimento` itself (`dias_atraso=0`) and non-zero from `dias_atraso=1`.
