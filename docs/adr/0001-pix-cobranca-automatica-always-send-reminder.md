# Always send the due-soon reminder regardless of cobrança-automática charge-generation outcome

**Status:** accepted

**Context.** Pix cobrança automática (Phase 2,
`docs/superpowers/specs/2026-06-07-pix-cobranca-automatica-design.md`) generates a Pix charge
`N` days before a parcela's `vencimento` and folds its `brcode` into the existing
`portal.parcela_due_soon` reminder email. The original draft proposed: on charge-generation
failure, skip the whole parcela (no email at all), with "tomorrow's run will retry."

**Decision.** The due-soon reminder is **always** enqueued for every selected parcela —
`brcode`/`pix_valido_ate` are present on success and simply absent on failure (rendering
today's "log in to pay" wording). Charge-generation outcome never gates whether the
notification goes out.

**Why.** `schedule_parcela_due_reminders` selects parcelas by an *exact-date* match
(`vencimento == today + dias_antes`, `notifications.py:140`). `target_date` shifts forward
by one day on every run, so a given parcela is selected on exactly one calendar day across
its entire lifetime — there is no "tomorrow's run re-attempts" for that parcela; tomorrow's
`target_date` will never match its `vencimento` again. Under skip-on-failure, a single
isolated PSP blip would silently and *permanently* drop that customer's only due-soon
reminder, with zero retry — a far worse outcome than "the email arrived without the Pix
convenience this once." Decoupling "send the reminder" from "charge generation succeeded"
guarantees every customer always gets their heads-up; cobrança automática stays purely
additive on top of a notification customers already relied on pre-Phase-2.

**Considered options:**
- *Skip-the-parcela-on-failure, retry tomorrow* (original draft) — rejected: the retry
  never actually happens (see above); silently drops reminders on any PSP blip.
- *Widen the selection query into a retry window* (e.g. `vencimento BETWEEN target_date AND
  target_date + buffer`, with per-parcela dedup) — rejected: bigger surgery to the existing
  query shape and idempotency-key semantics than the problem warrants, for a feature whose
  whole premise is "purely additive, no behavior change for opted-out tenants."

**Consequences.** The `_BREAKER_THRESHOLD` circuit breaker's role narrows from "stop the
batch on systemic failure" to "stop *attempting* charge-generation calls against a PSP
that's clearly down" — pure operational hygiene (fewer wasted PSP round-trips, one error
log line instead of dozens of warnings). It no longer gates whether any email goes out:
every parcela in scope gets exactly one due-soon email per run, with or without a `brcode`.
