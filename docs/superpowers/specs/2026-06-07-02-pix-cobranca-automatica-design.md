# Pix — Phase 2 (Cobrança automática)

> Closes the gap Phase 1 left open: today the customer must log into the portal and click "Pagar com Pix" to generate a charge. Phase 2 makes the system trigger that *same* mechanism proactively, ahead of the due date, and deliver the copia-e-cola directly in the existing due-soon reminder email — opt-in per tenant. Touches the `schedule_parcela_due_reminders` cron job, the `portal.parcela_due_soon` template, and adds two new per-tenant business rules.
>
> **This phase is small because Phase 1's CobV redesign did the structural work.** Phase 1 creates one long-lived charge per parcela, ever — idempotent, calendar-anchored to `vencimento`, payable early, on time, or late — behind a single shared core (`PixService._ensure_charge`). Phase 2 doesn't add a third charge-creation path; it **triggers the existing one on a schedule** and **changes what the reminder email says**. What's left is a scheduling decision, a notification-routing decision, and a template change.
>
> **Predecessor:** Phase 1 — Efí Pix Provider (`2026-06-07-01-efi-pix-provider-design.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md:378` — "FASE 2 — Cobrança automática"

## Goal

For tenants that opt in, the system proactively triggers Pix-charge generation `N` days before each parcela's `vencimento` (tenant-configurable, default 3) and folds the copia-e-cola directly into the existing due-soon reminder email — the customer can pay straight from their inbox without logging into the portal. Tenants that don't opt in see **no behavior change**: same fixed 3-day reminder, same "log in to pay" wording, same on-demand flow.

## In scope

### 1. New per-tenant business rules

Two new keys in `_RULE_DEFAULTS` (`rules_service.py`), following the convention `incluir_iof_default`/`rateio_ipva_meses_default` establish — `BusinessRule` rows, `RulesService.get_rules(tenant_id)` fills missing keys from defaults, surfaced in the admin business-rules schema/UI:

```python
"pix_cobranca_automatica_habilitada": (False, "Gerar Pix automaticamente antes do vencimento"),
"pix_cobranca_automatica_dias_antes": (3,     "Dias de antecedência para gerar Pix automático"),
```

`pix_cobranca_automatica_dias_antes` defaults to `3` — the same value `schedule_parcela_due_reminders` already hardcodes — so a tenant that flips the toggle on without touching the lead-time gets *only* the new Pix-in-email behavior, not a timing change.

**Validation cap: 1 to 30 days.** CobV is calendar-native and long-lived regardless of when it's first created — generating a charge 3 days early or 25 days early produces the same artifact, just sooner. This cap is plain input sanitization (prevents a fat-fingered `9999` from producing a nonsensical "27-year" reminder schedule). 1–30 covers every realistic cadence. Enforced in `RulesService.update`: when `chave == "pix_cobranca_automatica_dias_antes"`, reject values outside `[1, 30]` with `AppError`. `BusinessRuleUpdateIn.valor` is `Any` (untyped), and no existing rule has bounds at the schema layer, so write-time validation lives here.

**Cascading edits:**

- `schemas/business_rules.py` (`BusinessRulesOut`): add `pix_cobranca_automatica_habilitada: bool` and `pix_cobranca_automatica_dias_antes: int` (plain `int` — enforcement is in the service, not the schema).
- `api/business_rules.py` (`get_business_rules`): the endpoint constructs `BusinessRulesOut` field-by-field; add both new keyword args (`bool(rules["pix_cobranca_automatica_habilitada"])`, `int(rules["pix_cobranca_automatica_dias_antes"])`). Omitting them causes a Pydantic validation error on the GET response.
- `services/rules_service.py` (`RulesService.update`): add the `[1, 30]` guard for `pix_cobranca_automatica_dias_antes`.

**New seed migration** (`011_seed_pix_cobranca_automatica_rules.py`), mirroring `010_seed_ipva_emplacamento_rules.py` exactly: `INSERT ... SELECT ... FROM tenants ... ON CONFLICT (tenant_id, chave) DO NOTHING`, casting `false`/`3` to `jsonb`. Makes both rules visible and editable in the admin UI for existing tenants immediately after migration — matches why `010` exists despite `RulesService` already back-filling defaults at read time.

### 2. The system-trigger entry point

A thin wrapper over the shared `_ensure_charge` core (Phase 1 §3), named and wired here:

```python
async def create_auto_charge_for_parcela(self, parcela_payment_id: uuid.UUID) -> PixCharge:
    """System-triggered. No RequestContext, no ownership check (cron is pre-scoped
    by tenant + clientless filtering at the query level), no pix_link notification —
    the due-soon email *becomes* the delivery vehicle (§4). Raises on provider failure
    so the cron can apply its failure policy (§3)."""
    parcela = await self._s.get(ParcelaPayment, parcela_payment_id)
    return await self._ensure_charge(parcela)
```

That's the entire method. No TTL parameter, no duplicated provider-call/persistence/idempotent-reuse/`PayerInfo` logic — `_ensure_charge` already is that logic, shared. If the customer manually generates a Pix first and the cron runs later (or vice versa), the shared idempotent-reuse path returns the same charge either way — no duplicate provider call, no duplicate row. There is exactly one charge, and either trigger finds or creates it.

### 3. `schedule_parcela_due_reminders` — tenant-aware lead time + charge generation

Today: one global `target_date = date.today() + timedelta(days=3)`, single query across all tenants, plain "heads up" email. New shape — **loop over tenants**. Justified because `dias_antes` is per-tenant-configurable (1–30 range) with no natural global default — a single global query would need to run once per distinct value or query the widest window and post-filter, both clumsier than looping. Tenant count is small ("loja de veículos de pequeno e médio porte"), so N+1 round-trips is the right tradeoff.

```python
async with session_factory() as outer_session:
    tenant_ids = list(await outer_session.scalars(select(Tenant.id)))  # no ORDER BY needed

for tenant_id in tenant_ids:
    async with session_factory() as session:  # one session per tenant — clean identity map, airtight isolation
        rules = await RulesService(session).get_rules(tenant_id)
        auto_charge_on = rules["pix_cobranca_automatica_habilitada"]
        dias_antes = rules["pix_cobranca_automatica_dias_antes"] if auto_charge_on else 3
        target_date = date.today() + timedelta(days=dias_antes)
        # ... existing query, scoped to this tenant_id + target_date ...

        svc = NotificationService(session)
        pix_service = PixService(session, ctx["pix_provider"], ctx["storage_backend"])
        consecutive_failures = 0
        breaker_tripped = False

        for parcela in parcelas:
            # ...existing client/sim lookups, clientless skip (unchanged)...
            payload = {
                ...,
                "dias_antes": dias_antes,  # for the subject template — see §4
            }
            if auto_charge_on and not breaker_tripped:
                try:
                    charge = await pix_service.create_auto_charge_for_parcela(parcela.id)
                    consecutive_failures = 0
                    payload["brcode"] = charge.brcode
                    payload["pix_valido_ate"] = (
                        charge.expires_at
                        .astimezone(ZoneInfo("America/Sao_Paulo"))
                        .strftime("%d/%m/%Y")
                    )  # BRT round-trip required — see §4
                except Exception as exc:
                    consecutive_failures += 1
                    logger.warning("auto pix charge failed", parcela_id=str(parcela.id), exc=str(exc), consecutive=consecutive_failures)
                    if consecutive_failures >= _BREAKER_THRESHOLD:
                        breaker_tripped = True
                        logger.error("auto pix charge breaker tripped for tenant", tenant_id=str(tenant_id))
                    # falls through — reminder always goes out without brcode

            await svc.enqueue(template_key="portal.parcela_due_soon", payload=payload, ...)

        await session.commit()
```

**Session per tenant** — `async with session_factory() as session:` opens inside the `for tenant_id` loop. Each tenant gets a fresh session: clean identity map, no stale objects from previous tenants, airtight failure isolation — an exception in tenant N rolls back only that session; tenants 1..N-1's sessions are already closed and committed. `PixService` and `NotificationService` are constructed inside the same `async with` block so they share the session.

**Disabled tenants get exactly today's behavior** — `dias_antes = 3`, no `brcode`/`pix_valido_ate` in payload, template renders existing wording. Nothing changes unless a tenant enables the feature.

**Failure policy — the reminder always goes out; charge-generation is best-effort** (see [ADR-0001](../../adr/0001-pix-cobranca-automatica-always-send-reminder.md)):

The cron's parcela-selection query is an exact-date match (`vencimento == target_date`). `target_date` shifts forward one day per run, so a given parcela is selected on exactly **one** calendar day across its entire lifetime — there is no "tomorrow's run re-attempts." Skipping a parcela on charge-gen failure therefore silently and permanently drops that customer's only due-soon reminder over a single PSP blip. The policy instead:

1. **Charge generated successfully**: `brcode`/`pix_valido_ate` present, copia-e-cola block renders.
2. **Isolated failure (< `_BREAKER_THRESHOLD` = 3 consecutive)**: email still goes out without `brcode`/`pix_valido_ate` (renders today's "log in to pay" wording), warning logged, counter increments.
3. **Breaker trips (≥ 3 consecutive)**: `breaker_tripped = True`, error logged once, `create_auto_charge_for_parcela` not attempted for the rest of that tenant's run — every remaining parcela still gets its email. Counter is per-tenant-per-run; no cross-run state; self-heals on the next run.

`_BREAKER_THRESHOLD`'s only job is stopping wasted PSP calls once an outage is confirmed. It never gates whether an email goes out.

Idempotency key: `portal.parcela_due_soon:{parcela.id}:{target_date.isoformat()}` — unchanged shape, now keyed off the per-tenant `target_date`.

### 4. Template `portal.parcela_due_soon`

**`subject.txt`:** today hardcodes `"Lembrete: Parcela {{ parcela_num }} vence em 3 dias"`. Change to:

```
Lembrete: Parcela {{ parcela_num }} vence em {{ dias_antes | default(3) }} dias
```

`| default(3)` handles outbox rows enqueued before the deploy — their payload has no `dias_antes` key, and Jinja2's default `Undefined` renders as empty string without the filter. Post-deploy rows carry the actual value; pre-deploy rows render `"3"` as before.

**`body.txt` / `body.html`:** extend with a conditional copia-e-cola block:

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
Equipe FinancialSim
```

`body.html` gets the equivalent conditional. The `{% if brcode %}` guard is falsy for undefined (Jinja2 default), so old outbox rows without `brcode` render the else branch correctly.

**`pix_valido_ate` requires a BRT round-trip.** `PixCharge.expires_at` is persisted as UTC but represents 23:59:59 `America/Sao_Paulo` (Phase 1 §3b stores it as `datetime.combine(valid_through, time(23,59,59), tzinfo=BRT).astimezone(UTC)`). 23:59:59 BRT is 02:59:59 UTC the *next* calendar day — a naive `.date()` or `.isoformat()` on the stored value is off by one. The payload must convert back: `charge.expires_at.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")` — symmetric with the write side. No QR image: brcode text only (sidesteps signed-URL TTL coordination; `brcode` is a plain string with no expiry of its own).

### Tests

- `create_auto_charge_for_parcela`: thin-wrapper assertions only — calls `_ensure_charge` with the right `parcela`, no `RequestContext` required, no `pix_link` notification enqueued, provider exception propagates. (Idempotent-reuse/`PayerInfo`/QR-persistence behavior is Phase 1's shared-core test responsibility.)
- `schedule_parcela_due_reminders`:
  - Disabled tenant → `target_date = today+3`, `dias_antes=3` in payload, no `brcode`/`pix_valido_ate` (regression-pinned to today's exact behavior).
  - Enabled tenant with custom `dias_antes` → correct `target_date`, `dias_antes` in payload, `brcode`/`pix_valido_ate` (BRT-correct date) present.
  - Isolated failure (1–2 consecutive) → `enqueue` still called for that parcela, no `brcode`/`pix_valido_ate`, warning logged, counter resets on next success.
  - Breaker (3rd consecutive failure) → `breaker_tripped = True`, error logged once, `create_auto_charge_for_parcela` not called again for that tenant's run (call count stays flat), but all remaining parcelas still enqueued; next tenant starts fresh.
  - Clientless-proposal skip preserved.
  - Customer who manually generated a charge first → cron's call returns the same charge, no duplicate.
- `RulesService.update`: `pix_cobranca_automatica_dias_antes` rejects values outside 1–30 (`AppError`).
- Template rendering:
  - Subject renders `dias_antes` correctly for disabled default (`3`) and custom enabled value (e.g. `7`); old payload without `dias_antes` key renders `"3"` via `| default(3)`.
  - Body with `brcode`/`pix_valido_ate` → copia-e-cola block renders; `pix_valido_ate` shows BRT calendar day (e.g. `expires_at = 2026-08-16T02:59:59Z` → `"15/08/2026"`, not `"16/08/2026"`).
  - Body without `brcode` → "log in to pay" wording, unchanged.
- Seed migration: both rows present with correct defaults for pre-existing tenants after upgrade; `downgrade` removes them.

## Out of scope

- QR image in the cobrança automática email — brcode text only.
- Charge regeneration/retry: not a concept under CobV. The same charge is valid from creation through `vencimento + validadeAposVencimento` days. If it goes unpaid past that window, the parcela is in FASE 3/4 territory.
- WhatsApp/SMS/link-de-pagamento delivery — later roadmap phases.
- Any change to the on-demand `create_charge_for_parcela`/`pix_link` flow — unchanged from Phase 1.
- Per-tenant Efí accounts, mTLS/IP allowlisting — unchanged from Phase 1's out-of-scope list.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Tenant enables cobrança automática but cron silently never generates anything (e.g. rules lookup bug) | Tests pin both branches (`enabled`/`disabled`) of tenant-aware target-date logic; disabled-branch regression test catches accidental breakage of the default path |
| Exact-date selection (`vencimento == target_date`) means a parcela is selected on exactly one calendar day — a "skip on failure, retry tomorrow" policy would permanently drop the reminder on a single PSP blip | Reminder always enqueued regardless of charge-gen outcome ([ADR-0001](../../adr/0001-pix-cobranca-automatica-always-send-reminder.md)); `_BREAKER_THRESHOLD` only stops wasted PSP calls, never gates the email |
| Per-tenant loop with live PSP calls; uncaught exception mid-run | One session per tenant (`async with session_factory()` inside the loop) — each session commits and closes before the next opens; exception in tenant N cannot affect N-1's committed state |
| `pix_valido_ate` off-by-one if formatted naively from UTC-stored `expires_at` | BRT round-trip required: `charge.expires_at.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")`; template-rendering tests assert BRT-correct day |
| `pix_valido_ate` could drift if `pix_validade_apos_vencimento_dias` rule is changed after charges go out | Template renders `PixCharge.expires_at` (fixed at creation time), not a live rule re-read — always matches what Efí will actually honor |
| New `BusinessRule` keys not seeded for existing tenants → not visible in admin UI until explicitly set | Seed migration mirrors `010_seed_ipva_emplacamento_rules.py` — `ON CONFLICT DO NOTHING` upsert for all existing tenants |

## Acceptance checklist

- [ ] Tenant with `pix_cobranca_automatica_habilitada=True` and default `dias_antes=3`: parcela due in 3 days gets a charge generated, due-soon email subject says "vence em 3 dias", body contains `brcode` and `pix_valido_ate` as plain text.
- [ ] Tenant with `pix_cobranca_automatica_habilitada=False` (default for all existing tenants post-migration): due-soon email is identical to today — fixed 3-day window, "vence em 3 dias" subject, no Pix, "log in to pay" wording.
- [ ] Tenant with `pix_cobranca_automatica_habilitada=True` and custom `dias_antes=7`: subject says "vence em 7 dias".
- [ ] `pix_cobranca_automatica_dias_antes` outside 1–30 → `AppError` from `RulesService.update`; not silently clamped or accepted.
- [ ] Customer who manually generates Pix before the cron (or vice versa): both triggers resolve to the same charge via `_ensure_charge` — no duplicate provider call, no duplicate row.
- [ ] `pix_valido_ate` shown to the customer is the BRT calendar day — e.g. `expires_at = 2026-08-16T02:59:59Z` displays as `15/08/2026`, not `16/08/2026`.
- [ ] Isolated PSP failure (1–2 consecutive): due-soon email still sent (no `brcode`/`pix_valido_ate`, "log in to pay" wording), warning logged, no exception escapes the cron.
- [ ] Systemic PSP failure (≥3 consecutive in one tenant's run): breaker trips, `create_auto_charge_for_parcela` not attempted again for that tenant's remaining parcelas, all still get the email, error logged once, next tenant starts fresh.
- [ ] Per-tenant session isolation is structural: `async with session_factory()` inside the tenant loop; each session closes and commits independently.
- [ ] Clientless proposals skipped for cobrança automática generation (same guard as Phase 1 §2b).
- [ ] Admin business-rules UI shows and allows editing both new keys for every tenant immediately after migration.
- [ ] On-demand "Pagar com Pix" portal flow unaffected — Phase 1's test suite passes unchanged.
