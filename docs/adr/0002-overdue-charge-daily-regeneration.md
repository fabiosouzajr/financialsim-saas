# ADR-0002 — Overdue CobV charges regenerated daily (not stored-rate comparison)

**Status:** Accepted
**Date:** 2026-06-09
**Context:** Fase 3 — Inadimplência

---

## Context

CobV charges have juros/multa baked in at creation time — Efí cannot update the rates on an existing charge. A charge created before Fase 3 (zero rates) or created on a previous day (yesterday's interest accrual) will show the wrong amount to the customer.

Three approaches were considered for keeping overdue charges current:

**A. Store rates on `PixCharge`** — add `multa_pct`/`juros_pct` columns; compare against current rules on each `_ensure_charge` call; regenerate on mismatch. Requires a schema migration and rate-change detection logic.

**B. Accept staleness** — never regenerate. Customers on zero-rate charges (created before Fase 3) pay the original amount until the charge expires naturally (`vencimento + validadeAposVencimento` days, default 60). Simpler, but silent under-collection during the transition window.

**C. Daily regeneration (chosen)** — regenerate any overdue charge that was created on a previous BRT calendar day (`_created_before_today_brt`). No schema change. Handles both the Fase-3 deploy transition and ongoing daily accrual in one mechanism.

## Decision

Option C: `_ensure_charge` cancels and recreates an overdue charge when:
1. `parcela.status == overdue`
2. `rates_past_grace` (i.e., `dias_atraso > carencia_dias` and non-zero rates configured)
3. The existing charge was created before today (BRT)

## Consequences

- **`cancel_charge` becomes load-bearing** for overdue parcelas — it must not silently fail in ways that leave a stale charge active. Current contract (errors swallowed, old charge stays pending) is acceptable: worst case is the customer pays the stale amount for one more day.
- **One PSP cancel + create per overdue parcela per day** — bounded by the number of overdue parcelas, not by customer click rate. Acceptable for small/mid dealership scale.
- **`PixProvider.cancel_charge` is now semantically required** for any real provider — not just a cleanup convenience. A future provider that lacks cancel support would need a workaround.
- **`carencia_dias` field is NOT passed to the CobV body** — the BACEN schema has no `dataInicio` on juros/multa objects. Carência is enforced by passing zero rates during the grace period.
