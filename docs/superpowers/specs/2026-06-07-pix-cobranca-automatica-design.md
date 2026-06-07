# Pix — Phase 2 (Cobrança automática)

> Closes the gap Phase 1 left open: today the customer must log into the portal and click "Pagar com Pix" to generate a charge. Phase 2 makes the system trigger that *same* mechanism proactively, ahead of the due date, and deliver the copia-e-cola directly in the existing due-soon reminder email — opt-in per tenant. Touches the `schedule_parcela_due_reminders` cron job, the `portal.parcela_due_soon` template, and adds two new per-tenant business rules.
>
> **This phase got dramatically smaller after Phase 1's redesign.** The original draft of this spec spent most of its weight on a new `PixService.create_auto_charge_for_parcela` method, a hand-rolled TTL computation stretching a short-lived charge across days, and a private helper duplicating most of the on-demand creation path. None of that exists anymore: Phase 1 redesigned its foundation onto Efí's due-date charge type (CobV) and now creates **one long-lived charge per parcela, ever** — idempotent, calendar-anchored to `vencimento`, payable whether the customer pays early, on time, or late — as a single shared core (`PixService._ensure_charge`) behind two thin entry points. Phase 2 doesn't add a third charge-creation path; it just **triggers the existing one on a schedule** and **changes what the reminder email says**. What's left is a scheduling decision, a notification-routing decision, and a template change.
>
> **Predecessor:** Phase 1 — Efí Pix Provider (`2026-06-07-efi-pix-provider-design.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md:378` — "FASE 2 — Cobrança automática"

## Goal

For tenants that opt in, the system proactively triggers Pix-charge generation `N` days before each parcela's `vencimento` (tenant-configurable, default 3) and folds the copia-e-cola directly into the existing due-soon reminder email — the customer can pay straight from their inbox without logging into the portal. Tenants that don't opt in see **no behavior change**: same fixed 3-day reminder, same "log in to pay" wording, same on-demand flow.

## In scope

### 1. New per-tenant business rules

Two new keys in `_RULE_DEFAULTS` (`rules_service.py`), following the exact convention `incluir_iof_default`/`rateio_ipva_meses_default` already establish — `BusinessRule` rows, `RulesService.get_rules(tenant_id)` fills missing keys from defaults, surfaced in the admin business-rules schema/UI:

```python
"pix_cobranca_automatica_habilitada": (False, "Gerar Pix automaticamente antes do vencimento"),
"pix_cobranca_automatica_dias_antes": (3,     "Dias de antecedência para gerar Pix automático"),
```

`pix_cobranca_automatica_dias_antes` defaults to `3` — the same value `schedule_parcela_due_reminders` already hardcodes — so a tenant that flips the toggle on without touching the lead-time gets *only* the new Pix-in-email behavior, not a timing change.

**Validation cap on `pix_cobranca_automatica_dias_antes` — 1 to 30 days.** Under the old Cob-stretching design, this cap mattered because a large `dias_antes` meant a fragile short-lived charge would need stretching across a long, exposed window — a real technical risk worth bounding tightly. **That risk is now structurally gone**: Phase 1's CobV-based charge is calendar-native and long-lived regardless of when it's first created — generating it 3 days early or 25 days early produces the *same* artifact, just sooner. So this cap is no longer load-bearing for charge-mechanism safety; it's plain input sanitization, preventing a fat-fingered `9999` from producing a nonsensical "remind the customer about a bill due in 27 years" schedule. **1–30 covers every realistic reminder cadence** (most reminder systems use 1–7 days; a tenant might reasonably want a month's notice on a large parcela) without inviting silliness. Enforced as a `Field(ge=1, le=30)` constraint on `BusinessRulesSchema.pix_cobranca_automatica_dias_antes` (schema-layer validation — same place type constraints for other numeric rules already live), not a database constraint.

**New seed migration** (`011_seed_pix_cobranca_automatica_rules.py` or next free number), mirroring `010_seed_ipva_emplacamento_rules.py` exactly: `INSERT ... SELECT ... FROM tenants ... ON CONFLICT (tenant_id, chave) DO NOTHING`, casting `false`/`3` to `jsonb`. Makes both rules visible/editable in the admin UI for existing tenants immediately, not only once a tenant explicitly sets one (matches why `010` exists despite `RulesService` already back-filling defaults at read time).

Cascading edits to the schema layer (`schemas/business_rules.py`, `BusinessRulesSchema`): two new fields, `pix_cobranca_automatica_habilitada: bool` and `pix_cobranca_automatica_dias_antes: int = Field(ge=1, le=30)` — same pattern as `incluir_iof_default`/`rateio_ipva_meses_default`, plus the new bound.

### 2. The system-trigger entry point (named and wired here, per Phase 1 §3)

Phase 1's redesign deliberately deferred *naming* the cron-facing entry point to whichever phase actually needs to call it — that's this one. A thin wrapper over the shared `_ensure_charge` core (Phase 1 §3):

```python
async def create_auto_charge_for_parcela(self, parcela_payment_id: uuid.UUID) -> PixCharge:
    """System-triggered. No RequestContext, no ownership check (cron is pre-scoped
    by tenant + clientless filtering at the query level), no pix_link notification —
    the due-soon email *becomes* the delivery vehicle (§4); sending both would
    double-notify the customer about the same charge. Raises (does not swallow)
    on provider failure — propagates so the cron can apply its failure policy (§3)."""
    parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
    return await self._ensure_charge(parcela)
```

That's the entire method. No TTL parameter, no duplicated provider-call/persistence/idempotent-reuse/`PayerInfo` logic to keep in sync with the customer-facing path — `_ensure_charge` already *is* that logic, shared. **If the customer manually generates a Pix first and the cron runs later (or vice versa), the shared idempotent-reuse path returns the same charge either way** — no duplicate provider call, no duplicate row, no need to reason about "which trigger owns this charge." There is exactly one charge, and either trigger can find or create it.

### 3. `schedule_parcela_due_reminders` — tenant-aware lead time + charge generation

Today: one global `target_date = date.today() + timedelta(days=3)`, single query across all tenants, plain "heads up" email. New shape — **loop over tenants** (a new pattern for this codebase: every existing cron, including today's version of this job, queries globally across tenants in one shot — `mark_overdue_parcelas`, `schedule_parcela_due_reminders`. Justified here because `dias_antes` is per-tenant-configurable with a 1–30 range and no natural global default that fits every tenant — a single global query would need to either run once per distinct configured value, or query the widest possible window and post-filter, both clumsier than just looping. Tenant count is small — "loja de veículos de pequeno e médio porte" per the roadmap doc — so N+1 round-trips is the right tradeoff over either alternative):

```python
for tenant_id in <all tenant ids>:
    rules = await RulesService(session).get_rules(tenant_id)
    auto_charge_on = rules["pix_cobranca_automatica_habilitada"]
    dias_antes = rules["pix_cobranca_automatica_dias_antes"] if auto_charge_on else 3
    target_date = date.today() + timedelta(days=dias_antes)
    # ... existing query, scoped to this tenant + target_date ...

    consecutive_failures = 0
    for parcela in parcelas:
        ...existing client/sim lookups, clientless skip (unchanged)...
        payload = {... existing fields ...}
        if auto_charge_on and consecutive_failures < _BREAKER_THRESHOLD:
            try:
                charge = await pix_service.create_auto_charge_for_parcela(parcela.id)
                consecutive_failures = 0
                payload["brcode"] = charge.brcode
            except Exception as exc:
                consecutive_failures += 1
                logger.warning("auto pix charge failed", parcela_id=..., exc=str(exc), consecutive=consecutive_failures)
                if consecutive_failures < _BREAKER_THRESHOLD:
                    continue  # isolated failure — skip the whole parcela this run, no half-useful email
                logger.error("auto pix charge breaker tripped — degrading to plain reminders for rest of tenant's run")
                # falls through: enqueue plain reminder (no brcode) for this + all subsequent parcelas this tenant/run
        await svc.enqueue(template_key="portal.parcela_due_soon", payload=payload, ...)
```

Note what's *not* here anymore relative to the original draft: no `expires_in` computation, no `ZoneInfo`/BRT-anchoring in this file (that logic now lives once, in Phase 1's `_ensure_charge`/`EfiPixProvider`, used identically by every trigger — not duplicated per-cron). The cron's only remaining charge-related job is "decide whether and when to ask for one, and what to do if asking fails."

**Disabled tenants get exactly today's behavior** — `dias_antes = 3`, no `brcode` in payload, template renders the existing wording. This is the backward-compatibility seam: nothing about the existing flow changes unless a tenant flips the toggle.

**Failure policy — two tiers, isolated vs. systemic** (per design discussion):

1. **Isolated failure** (< `_BREAKER_THRESHOLD` = 3 consecutive): skip the whole parcela, no email — your original call. Recovery: tomorrow's run re-attempts if the parcela is still inside the `dias_antes` window.
2. **Systemic failure** (≥ 3 consecutive — Efí auth/cert/outage, not a blip): circuit breaker trips, **degrading the rest of that tenant's run to plain reminders** (no `brcode`, same wording disabled tenants get) rather than continuing to silently skip everyone. Converts "every customer of every enabled tenant gets nothing today" into "every customer still gets a heads-up, just without the auto-Pix convenience for one cycle." Counter is per-tenant-per-run — scoped to the loop above, no cross-run state, no new tables. Self-heals: tomorrow's run starts the counter fresh and retries Pix generation normally.

Either way, the on-demand "Pagar com Pix" portal flow is untouched and always available as the universal fallback — cobrança automática is purely additive on top of it.

Idempotency key stays `portal.parcela_due_soon:{parcela.id}:{target_date.isoformat()}` — unchanged shape, now keyed off the per-tenant `target_date`.

### 4. Template `portal.parcela_due_soon`

Extended to conditionally render a copia-e-cola block when `brcode` is present in the payload:

```jinja2
Olá {{ user_name }},

Sua Parcela {{ parcela_num }} ({{ valor_parcela }}) vence em {{ vencimento }}.
{% if brcode %}
Pague agora mesmo via Pix — copie o código abaixo no app do seu banco:

{{ brcode }}

O código é válido até {{ pix_valido_ate }}.
{% else %}
Acesse o portal para gerar o Pix e efetuar o pagamento.
{% endif %}

Atenciosamente,
Equipe FinacialSim
```

(Illustrative — exact wording/HTML mirrors the existing `parcela_due_soon`/`pix_link` templates' tone and structure; `body.html` gets the equivalent conditional.) **One small wording change from the original draft:** "válido até o vencimento" → "válido até `{{ pix_valido_ate }}`" — under the old Cob-stretching design the charge's expiry *was* the vencimento; under the redesigned CobV foundation it's `vencimento + pix_validade_apos_vencimento_dias` (default 60 days later, Phase 1 §3a). Saying "valid until the due date" would now be **wrong** — understating how long the customer actually has, and contradicting what happens if they pay a few weeks late and it still works. The cron payload gains one field, `pix_valido_ate = charge.expires_at` (formatted), threaded alongside `brcode`. No QR image — copia-e-cola text only (decided: sidesteps signed-URL TTL coordination entirely, since `brcode` is a plain string with no expiry of its own).

### Tests

- `create_auto_charge_for_parcela`: thin-wrapper assertions only — calls `_ensure_charge` with the right `parcela`, no `RequestContext` required, no `pix_link` notification enqueued, provider exception propagates (not swallowed). (TTL/`PayerInfo`/idempotent-reuse/QR-persistence behavior is now Phase 1's shared-core test responsibility — not duplicated here.)
- `schedule_parcela_due_reminders`: tenant with `pix_cobranca_automatica_habilitada=False` → `target_date = today+3`, no `brcode` in payload (today's exact behavior, regression-pinned); tenant with it `True` and custom `dias_antes` → correct `target_date`, `brcode` and `pix_valido_ate` present; isolated charge-creation failure (1-2 consecutive) → parcela skipped, no `enqueue` call, warning logged, counter resets on next success; **circuit breaker** — 3rd consecutive failure trips it, that parcela *and all subsequent ones in the same tenant's run* get a plain reminder (`enqueue` called, no `brcode`, error logged once), next tenant in the loop starts with a fresh counter; clientless-proposal skip preserved; customer who manually generated a charge first → cron's call returns the same charge, no duplicate.
- `BusinessRulesSchema`: `pix_cobranca_automatica_dias_antes` rejects values outside 1–30 (schema validation, not DB constraint).
- Template rendering: with `brcode`/`pix_valido_ate` → copia-e-cola block renders with the correct validity date; without → existing "log in to pay" wording renders unchanged.
- Seed migration: `pix_cobranca_automatica_habilitada`/`pix_cobranca_automatica_dias_antes` rows present with correct defaults for pre-existing tenants after upgrade; `downgrade` removes them.

## Out of scope

- QR image in the cobrança automática email (decided: brcode text only — no signed-URL TTL coordination needed).
- **Regeneration/retry of a pre-generated charge as it nears expiry — now structurally not a concept.** Under the old Cob-stretching design this was a real "out of scope, but here's why it's safe to skip" call. Under the redesigned CobV foundation, there is nothing to regenerate: the same charge is valid from creation through `vencimento + 60 days` (default), the *only* charge that will ever exist for that parcela. If it goes unpaid past that window, the parcela has moved into FASE 3/4 (Inadimplência/Renegociação) territory — a different phase's problem, not a "the Pix charge expired, make a fresh one" problem.
- WhatsApp/SMS/Link-de-pagamento delivery — later roadmap phases (FASE 5 — Integração WhatsApp) and the link-de-pagamento functional requirement remain deferred.
- Any change to the on-demand `create_charge_for_parcela`/`pix_link` flow — stays exactly as Phase 1 (redesigned) left it; this phase is purely additive (one new thin entry point, a cron branch, a template conditional).
- Per-tenant Efí accounts, mTLS/IP allowlisting — carried over unchanged from Phase 1's out-of-scope list.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Tenant enables cobrança automática but the cron silently never generates anything (e.g., rules lookup bug) — customer never gets the new Pix-in-email behavior, support ticket ensues | Tests pin both branches (`enabled`/`disabled`) of the tenant-aware target-date logic; the disabled-branch regression test ensures the default path is never accidentally broken |
| A systemic PSP outage (not a blip) would, under a pure "skip the whole parcela" policy, silently produce zero reminder emails for *every* customer of *every* cobrança-automática-enabled tenant that day — not just `dias_antes == 1` tenants | Per-tenant-per-run circuit breaker (`_BREAKER_THRESHOLD = 3` consecutive failures) degrades the rest of that run to plain reminders (today's wording, no `brcode`) — converts batch-wide silence into batch-wide graceful degrade. Self-heals next run (fresh counter); on-demand portal flow remains the universal fallback regardless |
| Template says "válido até {{ pix_valido_ate }}" but the underlying validity window (`pix_validade_apos_vencimento_dias`) is admin-editable — a tenant could change it after charges already went out, leaving old emails describing a now-stale validity date | Each `PixCharge.expires_at` is fixed at creation time and the template renders *that charge's* actual `expires_at`, not a live re-read of the current rule — emails always describe the charge they actually shipped with, never drift out of sync with what Efí will actually honor |
| New `BusinessRule` keys not seeded for existing tenants → admin UI shows them only after a tenant explicitly sets one, inconsistent with how `incluir_iof_default` etc. always appear | Seed migration mirrors `010_seed_ipva_emplacamento_rules.py` exactly — same `ON CONFLICT DO NOTHING` upsert-for-all-tenants pattern |

## Acceptance checklist

- [ ] Tenant with `pix_cobranca_automatica_habilitada=True` and default `dias_antes=3`: parcela due in 3 days gets a charge generated via the existing shared mechanism, and the due-soon email contains its `brcode` plus its actual `expires_at` as `pix_valido_ate` — both as copy-paste/plain text.
- [ ] Tenant with `pix_cobranca_automatica_habilitada=False` (the default for all existing tenants post-migration): due-soon email is byte-for-byte the same as today — fixed 3-day window, no Pix, "log in to pay" wording.
- [ ] `pix_cobranca_automatica_dias_antes` rejects values outside 1–30 at the schema layer (e.g., admin attempts to set `0` or `45` → validation error, not silently clamped or accepted).
- [ ] Customer who manually generates Pix before the cobrança automática cron runs (or vice versa): both triggers resolve to the *same* charge via `_ensure_charge`'s idempotent reuse — no duplicate provider call, no duplicate charge row, regardless of ordering.
- [ ] Isolated PSP failure (1-2 consecutive) during cobrança automática triggering: that parcela is skipped entirely (no email sent), warning logged, no exception escapes the cron job, counter resets on the next success.
- [ ] Systemic PSP failure (3+ consecutive within one tenant's run): circuit breaker trips — that parcela and all subsequent ones in the same tenant's run get a plain reminder (no `brcode`/`pix_valido_ate`, today's wording) instead of silence; error logged once; the next tenant in the loop is unaffected (fresh counter).
- [ ] Clientless proposals are skipped for cobrança automática generation exactly as they already are for the plain reminder (and as Phase 1 §2b guards on the on-demand path).
- [ ] Admin business-rules UI shows and allows editing both new keys for every tenant (pre-existing and newly created) immediately after the migration runs.
- [ ] On-demand "Pagar com Pix" portal flow is completely unaffected — verified by Phase 1's test suite passing unchanged.
