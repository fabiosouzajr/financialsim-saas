# Pix — Phase 2 (Cobrança automática)

> Closes the gap Phase 1 left open: today the customer must log into the portal and click "Pagar com Pix" to generate a charge (30-min TTL, on-demand). Phase 2 makes the system generate the charge proactively, ahead of the due date, and deliver the copia-e-cola directly in the existing due-soon reminder email — opt-in per tenant. Touches `PixService` (new system-creation method), the `schedule_parcela_due_reminders` cron job, the `portal.parcela_due_soon` template, and adds two new per-tenant business rules. No protocol/provider changes — builds entirely on Phase 1's `EfiPixProvider`/`PayerInfo` plumbing.
>
> **Predecessor:** Phase 1 — Efí Pix Provider (`2026-06-07-efi-pix-provider-design.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md:378` — "FASE 2 — Cobrança automática"

## Goal

For tenants that opt in, the system auto-generates a Pix charge `N` days before each parcela's `vencimento` (tenant-configurable, default 3) and folds the copia-e-cola directly into the existing due-soon reminder email — the customer can pay straight from their inbox without logging into the portal. Tenants that don't opt in see **no behavior change**: same fixed 3-day reminder, same "log in to pay" wording, same on-demand 30-min-TTL flow.

## In scope

### 1. New per-tenant business rules

Two new keys in `_RULE_DEFAULTS` (`rules_service.py`), following the exact convention `incluir_iof_default`/`rateio_ipva_meses_default` already establish — `BusinessRule` rows, `RulesService.get_rules(tenant_id)` fills missing keys from defaults, surfaced in the admin business-rules schema/UI:

```python
"pix_auto_charge_enabled":   (False, "Gerar Pix automaticamente antes do vencimento"),
"pix_auto_charge_dias_antes": (3,    "Dias de antecedência para gerar Pix automático"),
```

`pix_auto_charge_dias_antes` defaults to `3` — the same value `schedule_parcela_due_reminders` already hardcodes — so a tenant that flips the toggle on without touching the lead-time gets *only* the new Pix-in-email behavior, not a timing change.

**New seed migration** (`011_seed_pix_auto_charge_rules.py` or next free number), mirroring `010_seed_ipva_emplacamento_rules.py` exactly: `INSERT ... SELECT ... FROM tenants ... ON CONFLICT (tenant_id, chave) DO NOTHING`, casting `false`/`3` to `jsonb`. Makes both rules visible/editable in the admin UI for existing tenants immediately, not only once a tenant explicitly sets one (matches why `010` exists despite `RulesService` already back-filling defaults at read time).

Cascading edits to the schema layer (`schemas/business_rules.py`, `BusinessRulesSchema`): two new fields, `pix_auto_charge_enabled: bool` and `pix_auto_charge_dias_antes: int` — same pattern as `incluir_iof_default`/`rateio_ipva_meses_default`.

### 2. `PixService.create_auto_charge_for_parcela` — system-triggered creation

New method alongside `create_charge_for_parcela`, for the cron's system-level caller (no `RequestContext`, no per-request ownership check — the cron is trusted, it already filters by tenant and skips clientless proposals at the query level):

```python
async def create_auto_charge_for_parcela(
    self, parcela_payment_id: uuid.UUID, expires_in: int
) -> PixCharge:
```

Differs from `create_charge_for_parcela` in three ways, sharing everything else through a small private helper (`_create_charge`, taking `parcela`, `expires_in`, and a `notify: bool` flag) so the provider call, `PixCharge` persistence, idempotent-reuse-of-pending-charge check, and `PayerInfo` construction (Phase 1 §2a — `Client.tipo`/`cpf_cnpj` → `document_type`/`document`) are written exactly once:

- **No `RequestContext`** — cron has no request, nothing to verify ownership against.
- **Parameterized `expires_in`** — replaces the hardcoded `1800` in `create_charge_for_parcela`.
- **No `pix_link` notification** — the due-soon email *becomes* the delivery vehicle (§4); sending both would double-notify the customer about the same charge.

Raises (does not swallow) on provider failure — propagates `ValidationError`/SDK exceptions from Phase 1's error-translation boundary so the cron can apply the chosen failure policy (§3).

**TTL computation** (caller's responsibility, lives in the cron job — `PixService` stays a thin persistence/provider layer, doesn't know about "due dates"):

```python
expires_at = datetime.combine(parcela.vencimento, time(23, 59, 59), tzinfo=UTC)
expires_in = int((expires_at - datetime.now(UTC)).total_seconds())
```

One charge spans the full window from creation to end-of-due-date — no regeneration, matches the "long-lived charge" decision. If an existing pending (non-expired) charge already covers the parcela — e.g., the customer manually generated one first — the shared idempotent-reuse path returns it unchanged; no duplicate charge, no duplicate provider call.

### 3. `schedule_parcela_due_reminders` — tenant-aware lead time + charge generation

Today: one global `target_date = date.today() + timedelta(days=3)`, single query across all tenants, plain "heads up" email. New shape — iterate tenants, branch on their rules:

```python
for tenant_id in <distinct tenant ids with parcelas open in the lookahead window>:
    rules = await RulesService(session).get_rules(tenant_id)
    auto_charge_on = rules["pix_auto_charge_enabled"]
    dias_antes = rules["pix_auto_charge_dias_antes"] if auto_charge_on else 3
    target_date = date.today() + timedelta(days=dias_antes)
    # ... existing query, scoped to this tenant + target_date ...
    for parcela in parcelas:
        ...existing client/sim lookups, clientless skip (unchanged)...
        payload = {... existing fields ...}
        if auto_charge_on:
            try:
                charge = await pix_service.create_auto_charge_for_parcela(parcela.id, expires_in)
            except Exception as exc:
                logger.warning("auto pix charge failed, skipping reminder", parcela_id=..., exc=str(exc))
                continue  # skip the whole parcela this run — no half-useful email
            payload["brcode"] = charge.brcode
        await svc.enqueue(template_key="portal.parcela_due_soon", payload=payload, ...)
```

**Disabled tenants get exactly today's behavior** — `dias_antes = 3`, no `brcode` in payload, template renders the existing wording. This is the backward-compatibility seam: nothing about the existing flow changes unless a tenant flips the toggle.

**Failure policy — skip the whole parcela, no email** (per design discussion): if `create_auto_charge_for_parcela` raises (PSP error, timeout, validation), log a warning and `continue` — no reminder goes out for that parcela this run. Recovery: tomorrow's run re-attempts if the parcela is still inside the `dias_antes` window (i.e., `dias_antes > 1`); for `dias_antes == 1` a persistent failure means no automated reminder reaches the customer for that parcela, who falls back to manually generating Pix in the portal (the on-demand flow is untouched and always available). This matches the existing fallback story — the portal "Pagar com Pix" button keeps working exactly as before, auto-charge is additive.

Idempotency key stays `portal.parcela_due_soon:{parcela.id}:{target_date.isoformat()}` — unchanged shape, now keyed off the per-tenant `target_date`.

### 4. Template `portal.parcela_due_soon`

Extended to conditionally render a copia-e-cola block when `brcode` is present in the payload:

```
Olá {{ user_name }},

Sua Parcela {{ parcela_num }} ({{ valor_parcela }}) vence em {{ vencimento }}.
{% if brcode %}
Pague agora mesmo via Pix — copie o código abaixo no app do seu banco:

{{ brcode }}

O código é válido até o vencimento.
{% else %}
Acesse o portal para gerar o Pix e efetuar o pagamento.
{% endif %}

Atenciosamente,
Equipe FinacialSim
```

(Illustrative — exact wording/HTML mirrors the existing `parcela_due_soon`/`pix_link` templates' tone and structure; `body.html` gets the equivalent conditional.) No QR image — copia-e-cola text only (decided: sidesteps signed-URL TTL coordination entirely, since `brcode` is a plain string with no expiry of its own).

### Tests

- `create_auto_charge_for_parcela`: TTL passed through correctly to `provider.create_charge`; idempotent reuse of an existing pending charge (no duplicate provider call); `PayerInfo` built identically to `create_charge_for_parcela`; no `pix_link` notification enqueued; provider exception propagates (not swallowed).
- `schedule_parcela_due_reminders`: tenant with `pix_auto_charge_enabled=False` → `target_date = today+3`, no `brcode` in payload (today's exact behavior, regression-pinned); tenant with it `True` and custom `dias_antes` → correct `target_date`, `brcode` present; charge-creation failure → parcela skipped, no `enqueue` call, warning logged; clientless-proposal skip preserved.
- Template rendering: with `brcode` → copia-e-cola block renders; without → existing "log in to pay" wording renders unchanged.
- Seed migration: `pix_auto_charge_enabled`/`pix_auto_charge_dias_antes` rows present with correct defaults for pre-existing tenants after upgrade; `downgrade` removes them.

## Out of scope

- QR image in the auto-charge email (decided: brcode text only — no signed-URL TTL coordination needed).
- Regeneration/retry of a pre-generated charge as it nears expiry — the long-lived single-charge TTL policy makes this unnecessary; if it expires unpaid, the customer falls back to the on-demand portal flow (generates a fresh 30-min charge, unaffected by this phase).
- WhatsApp/SMS/Link-de-pagamento delivery — later roadmap phases (FASE 5 — Integração WhatsApp) and the link-de-pagamento functional requirement remain deferred.
- Any change to the on-demand `create_charge_for_parcela`/`pix_link` flow — stays exactly as Phase 1 left it; this phase is purely additive (a new method, a new cron branch, a new template conditional).
- Per-tenant Efí accounts, mTLS/IP allowlisting — carried over unchanged from Phase 1's out-of-scope list.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Tenant enables auto-charge but the cron silently never generates anything (e.g., rules lookup bug) — customer never gets the new Pix-in-email behavior, support ticket ensues | Tests pin both branches (`enabled`/`disabled`) of the tenant-aware target-date logic; the disabled-branch regression test ensures the default path is never accidentally broken |
| Long-lived charge (days) sits unpaid; underlying `EfiPixProvider`/Efí sandbox conventions lean toward short-lived charges — unverified how Efí's real API behaves with multi-day `calendario.expiracao` | Manual smoke-test step added to the runbook (or a follow-up note there): create an auto-charge-shaped charge (multi-day `expires_in`) against the Efí sandbox, confirm it's payable throughout the window, before enabling for any real tenant |
| Skip-the-whole-parcela failure policy means a persistent PSP outage near a `dias_antes == 1` tenant's window leaves customers with zero automated reminder for that cycle | Documented behavior (not silently swallowed): warning-logged per skipped parcela, customer's on-demand portal flow remains the universal fallback, unaffected by this phase |
| Sharing creation logic between `create_charge_for_parcela` (customer-facing) and `create_auto_charge_for_parcela` (system-facing) via a private helper risks the helper accumulating two callers' worth of special cases over time | Helper's contract kept narrow — provider call + persistence + idempotent reuse + `PayerInfo` only; the three differences (ctx/ownership, TTL, notification) stay in the public methods, not pushed into the shared helper |
| New `BusinessRule` keys not seeded for existing tenants → admin UI shows them only after a tenant explicitly sets one, inconsistent with how `incluir_iof_default` etc. always appear | Seed migration mirrors `010_seed_ipva_emplacamento_rules.py` exactly — same `ON CONFLICT DO NOTHING` upsert-for-all-tenants pattern |

## Acceptance checklist

- [ ] Tenant with `pix_auto_charge_enabled=True` and default `dias_antes=3`: parcela due in 3 days gets an auto-generated charge (TTL spanning to end of `vencimento` day) and the due-soon email contains its `brcode` as copy-paste text.
- [ ] Tenant with `pix_auto_charge_enabled=False` (the default for all existing tenants post-migration): due-soon email is byte-for-byte the same as today — fixed 3-day window, no Pix, "log in to pay" wording.
- [ ] Customer who manually generates Pix before the auto-charge cron runs: cron reuses the existing pending charge (no duplicate provider call, no duplicate charge row).
- [ ] PSP failure during auto-charge creation: that parcela is skipped entirely (no email sent), warning logged, no exception escapes the cron job (other tenants'/parcelas' processing continues).
- [ ] Clientless proposals are skipped for auto-charge generation exactly as they already are for the plain reminder (and as Phase 1 §2a guards on the on-demand path).
- [ ] Admin business-rules UI shows and allows editing both new keys for every tenant (pre-existing and newly created) immediately after the migration runs.
- [ ] On-demand "Pagar com Pix" portal flow (30-min TTL, `pix_link` notification) is completely unaffected — verified by the existing Phase 1/6 test suite passing unchanged.
