# Efí Pix Provider — Phase 1 (PIX básico real, fundação CobV)

> Implements the real PSP wiring that Phase 6 deferred: a working `EfiPixProvider` behind the existing `PixProvider` Protocol, replacing `StubExternalPixProvider`. **Redesigned from an earlier draft that targeted Efí's immediate-charge type (Cob/`expiracao`-in-seconds) — this version targets Efí's due-date charge type (CobV/`cobrança com vencimento`) instead, because every Pix charge in this domain traces back to a `parcela`, and every `parcela` has a `vencimento`. There is no "true immediate, no-due-date" charge concept here — Cob would be a dead-end abstraction.** Touches `PixService` (collapses charge creation into one idempotent, shared, dual-trigger core — see §3), the `PixProvider` Protocol (`PayerInfo`, date-based `create_charge`, `query_params`), plus one small deliberate guard (§2b — a clientless proposal can't be Pix-charged, applies to `fake` too). No DB schema or frontend changes; the fake-provider demo is otherwise unaffected.
>
> **Predecessor:** Phase 6 — Portal do cliente + Pix scaffold (`2026-05-28-saas-phase-6-portal-cliente-pix.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md` — "FASE 1 — PIX básico"
> **Companion:** Phase 2 — Cobrança automática (`2026-06-07-pix-cobranca-automatica-design.md`) builds *on top of* the mechanism this phase completes — it adds no new charge-creation logic of its own, only a proactive trigger and an email-delivery layer.

## Goal

`PIX_PROVIDER=efi` produces real PIX charges through Efí (Bank) using Efí's **due-date charge type (CobV — `/v2/cobv`)**, not the immediate-charge type (Cob — `/v2/cob`). One CobV charge is created per `parcela`, **ever** — on first need, whichever trigger fires first (a customer's "Pagar com Pix" click, or — once Phase 2 lands — the cron's lead-time window). That single charge, anchored to `calendario.dataDeVencimento = parcela.vencimento`, stays payable across the customer's entire realistic payment window: early, on time, or late — the same `brcode`/QR works throughout, no regeneration. End-to-end demo: staff/customer triggers "Pagar com Pix" → real Efí sandbox CobV charge created → customer pays via Efí's sandbox simulator → webhook confirms → `parcela` flips to `paid`, exactly as the fake-provider flow does today.

## Why CobV, not Cob (the redesign rationale)

The original draft of this spec built `EfiPixProvider` on Cob (`pix_create_charge`, `calendario.expiracao` — a duration in seconds from creation) because that's the SDK's most-documented "create a Pix charge" entry point, and it matched the fake provider's existing 30-minute-TTL shape. Two things surfaced during design review that make this the wrong foundation:

1. **Juros/multa on overdue parcelas.** A customer who clicks "Pagar com Pix" on an *overdue* parcela should get a charge reflecting interest/penalty — not a stale flat amount. Efí's CobV computes this natively: *"Se o pagamento for realizado após a data de vencimento, o sistema automaticamente calculará os juros e a multa, e o valor final será ajustado"* (confirmed against Efí's own blog/docs). Cob has no such concept — it would require hand-rolling penalty math the PSP already does for free. This also happens to be exactly what the roadmap's own FASE 3 ("Inadimplência — multa fixa configurável, juros diário configurável") asks for: CobV's `valor.juros`/`valor.multa`/`valor.desconto`/`valor.abatimento` fields *are* that requirement, not a separate batch job to design later.
2. **One mechanism, one lifecycle.** Cob (duration-from-creation, short-lived-by-design) and CobV (calendar-date-anchored, native penalty support) are architecturally distinct — Efí's own docs note an immediate charge can carry an expiration *or* a due date, never both. Building the on-demand flow on Cob while Phase 2's "cobrança automática" inevitably needs CobV (or a hand-stretched imitation of it) would mean two charge types, two SDK paths, two webhook-shape assumptions, two `PixCharge` lifecycles — for a system this size, that's pure accidental complexity. Standardizing on CobV for *every* Pix charge — on-demand and proactive alike — collapses that into one mechanism, one lifecycle, one webhook contract.

The practical consequence: there is no more "30-minute charge." `expires_in: int` (seconds-from-creation) disappears from the `PixProvider` Protocol entirely, replaced by a calendar-date-anchored validity window (§3). This is a deliberate behavior change from the Phase-6 fake-provider demo's TTL — and arguably better UX: a charge that's still mid-payment-attempt never silently dies under the customer.

## In scope

### 1. `EfiPixProvider` (`backend/finacialsim_saas/pix/efi.py`)

Implements `PixProvider` using the official `efipay` Python SDK (`pip install efipay`, confirmed on PyPI and at `github.com/efipay/sdk-python-apis-efi` — not currently in `pyproject.toml`, add it there as part of this work), sync/`requests`-based, wrapped in `asyncio.to_thread` — the same pattern this codebase already uses for sync libraries inside async code (`workers/tasks.py:292` for WeasyPrint, `storage/s3.py` for boto3).

```python
class EfiPixProvider:
    name = "efi"  # matches pix_provider selector value (renamed from generic "external" — see §4)

    def __init__(self, settings: Settings, client: EfiPay | None = None) -> None:
        self._client = client or EfiPay({
            "client_id": settings.efi_client_id,
            "client_secret": settings.efi_client_secret,
            "sandbox": settings.efi_sandbox,
            "certificate": settings.efi_certificate_path,
        })
        self._pix_key = settings.efi_pix_key
        self._webhook_secret = settings.pix_webhook_secret
```

The optional `client` param exists purely for test injection — production goes through `deps.get_pix_provider` (`EfiPixProvider(settings)`, unchanged call site); tests pass a `MagicMock()` directly. No monkeypatching, no dummy cert files needed, mirrors `PixService(session, provider, storage)`'s constructor-injection style.

| Protocol method | Efí REST call (via SDK) | Behavior |
|---|---|---|
| `create_charge` | `efi.pix_create_due_charge(params={"txid": txid}, body=body)` → `PUT /v2/cobv/:txid`, then `efi.pix_generate_qrcode(params={"id": loc_id})` → `GET /v2/loc/:id/qrcode` (CobV responses also carry `loc.id` — same QR-fetch flow as Cob, unchanged) | Builds `devedor` from `payer.document`/`payer.document_type` (`{"cpf": ...}` or `{"cnpj": ...}`); `valor.original` from `amount`; `chave` from settings; **`calendario = {"dataDeVencimento": due_date.isoformat(), "validadeAposVencimento": validity_days}`** (replaces Cob's `calendario.expiracao`). `juros`/`multa` sent as **explicit inert values** — `{"modalidade": <N>, "valorPerc": "0.00"}` — not omitted (§1b). Response gives `pixCopiaECola` (→ `brcode`) and `loc.id`; second call returns `imagemQrcode` — a base64 PNG with a `data:image/png;base64,` prefix that must be stripped before decoding into `qr_png_bytes`. Maps `calendario.dataDeVencimento + validadeAposVencimento` (end of that day, BRT-anchored — see §3b) to `expires_at`. SDK/network exceptions are caught here and re-raised as `ValidationError("Não foi possível gerar o PIX no momento, tente novamente")` — see §1c (Error translation). |
| `cancel_charge` | `efi.pix_update_due_charge(params={"txid": txid}, body={"status": ...})` → `PATCH /v2/cobv/:txid` | Errors logged and swallowed — `PixService.cancel_charges_for_proposal` already treats provider cancel failures as best-effort (`service.py:319-322`). **The exact cancellation status string for CobV must be verified against the SDK's `pix_update_due_charge.py` example before implementation** — CobV's lifecycle states are not guaranteed to mirror Cob's `REMOVIDA_PELO_USUARIO_RECEBEDOR` literally, even if the concept (recipient-initiated removal) carries over. |
| `verify_webhook` | — (local validation only) | **Unchanged from the original Cob-based design — Efí registers webhooks per-`chave` (the Pix key), not per-charge-type, so the delivered payload shape is identical regardless of whether the underlying charge was Cob or CobV.** Static token in the callback URL's query string (not body HMAC); synthesizes `WebhookEvent(status="paid", ...)` from `{"pix": [{"endToEndId", "txid", "chave", "valor", "horario", "infoPagador"}]}`, which carries no explicit status field — receiving a `pix[]` entry *is* the signal. This is the one piece of the original design the Cob→CobV swap doesn't touch at all. |

**SDK method names — verified directly against `efipay/sdk-python-apis-efi`'s own example files (not a placeholder):**

- **`pix_create_due_charge(params={"txid": txid}, body=body)`** is the txid-based CobV creation call (`PUT /v2/cobv/:txid`) — confirmed via `examples/pix/cobv/pix_create_due_charge.py`. Mirrors Cob's `pix_create_charge` exactly: caller supplies `txid` via `params`, Efí does not generate one server-side. **This is what makes the Cob→CobV swap mechanically clean** — `PixService`'s txid generation (`txid = str(charge_id).replace("-", "")[:35]`, `service.py:73-74`) and the webhook lookup (`select(PixCharge).where(PixCharge.txid == event.txid)`, `service.py:182-185`) carry over completely untouched; only the *creation* call's name and body shape change.
- **`pix_generate_qrcode(params={"id": loc_id})`** — unchanged from the Cob design; CobV creation responses also return a `loc.id`.
- **`pix_update_due_charge(params={"txid": txid}, body=...)`** is `PATCH /v2/cobv/:txid` — confirmed via `examples/pix/cobv/pix_update_due_charge.py`. Used for `cancel_charge`; exact cancellation `status` value is a pre-implementation verification item (see table above).

**1b — Juros/multa sent as explicit zero, not omitted (deliberate FASE-1 scope boundary).** CobV's request body always carries `juros`/`multa` sections (confirmed present in the SDK's own example body — not optional decoration). Rather than guess at what omitting them does, `EfiPixProvider` sends explicit "no charge" values. The exact `modalidade` integer code that means "apply nothing" must be read off the SDK's own `pix_create_due_charge.py` example body before implementation — same rigor §1's predecessor table applied to distinguishing `pix_create_charge` from `pix_create_immediate_charge`. **Why bother sending explicit zeros instead of, say, `None`/omission:** it means FASE 3 (Inadimplência) changes *only* the values flowing into these two fields — sourced from new per-tenant `BusinessRule` keys at that point — with zero Protocol or provider rework. The fields stay baked into `EfiPixProvider`'s body construction in this phase (not threaded through `PixProvider.create_charge`'s signature) — there is no tenant-configurable rate to pass yet, and adding the parameter now would be speculative surface for a need FASE 3 will define precisely. `desconto`/`abatimento` (renegotiation-discount concepts — FASE 4 territory) are omitted entirely; nothing in this phase or FASE 3 needs them.

**Known unknown — verify before launch, not a blocker to writing this spec:** one fetch of Efí's CobV docs returned the claim *"Charges with values between R$ 0.01 to R$ 10.00 are confirmed via Webhook; charges above R$ 10.00 remain active without confirmation, and there is no webhook in these cases."* Taken at face value for *production* CobV, this would mean typical-value parcela payments never fire a webhook — breaking reconciliation outright, which no PSP would ship as standard behavior. It almost certainly describes a **sandbox-simulator** quirk (it's suspiciously identical in shape to this same spec's own documented "sandbox charges ≤ R$10.01 auto-confirm" note, §6 step 7) bleeding into an AI-summarized fetch that dropped the qualifier. Folded into the runbook's manual smoke-test step (§6) as an explicit verify-and-correct checkpoint — confirm real webhook delivery for an above-R$10 sandbox payment before this goes anywhere near a real tenant.

### 1c. Error translation at the provider boundary

`create_charge_for_parcela` calls `provider.create_charge(...)` with no try/except (`service.py:76`) — fine for the fake provider (can't realistically fail), not fine for a real PSP that will occasionally hit network blips, Efí downtime, auth/cert issues, or payer-data validation rejections. Left untranslated, these surface as raw 500s (FastAPI's default handler — `main.py` only registers a handler for the app's own `AppError` hierarchy). `EfiPixProvider` catches SDK/`httpx`-level exceptions internally and re-raises as `ValidationError` with a user-facing PT-BR message, so the existing `AppError` handler formats them cleanly — entirely contained in `efi.py`, no `PixService` changes.

### 2. `PixProvider` Protocol changes (`pix/protocol.py`)

Three changes surfaced by Efí's real API and the CobV redesign. All are generic PIX-PSP concepts (not Efí-specific), so fixing them keeps the interface pluggable for any future provider:

**a) Structured payer identity.** Efí requires `devedor: {cpf, nome}` or `{cnpj, nome}` — distinct fields per document type, not a generic blob. The current `payer: str` (always passed as `""` — a placeholder never wired to real data, `service.py:81`) can't carry that. New dataclass, mirroring the existing `PixChargeData`/`WebhookEvent` convention:

```python
@dataclass
class PayerInfo:
    document: str          # CPF or CNPJ, digits only (punctuation stripped)
    document_type: Literal["cpf", "cnpj"]
    name: str
```

**Type comes from `Client.tipo` (already `pf`/`pj`, `models.py:380-382`), not from sniffing digit-count** — `Client.cpf_cnpj` is stored as-entered with punctuation (`client_service.py:108` does no normalization: `123.456.789-09` / `12.345.678/0001-90`), so length-based guessing would be both wrong (wrong length pre-strip) and fragile (malformed data could produce a misleading length post-strip). `PixService`'s shared charge-creation core (§3) looks up the `Client` (via `Proposal → Simulation → Client`), strips non-digits from `cpf_cnpj`, maps `tipo.pf → "cpf"` / `tipo.pj → "cnpj"`, and passes `PayerInfo(document=..., document_type=..., name=client.nome)`.

**b) New guard — clientless proposal can't be Pix-charged.** `Simulation.client_id` is nullable (`models.py:273-275`); `proposal_service.py:89` already shows `Proposal`s can exist with no linked `Client` (`client = ... if sim.client_id else None`). Staff (not just customers) can reach the charge-creation core for such a proposal's parcelas — the customer-ownership check only applies `if ctx.client_id is not None`. Rather than thread `payer=None` through to a real PSP (Efí's `devedor` is technically optional, but a Pix charge with no payer binding is a real gap for reconciliation/compliance), the shared core now raises `ValidationError("não é possível gerar Pix sem cliente vinculado à proposta")` when `sim.client_id is None` or the `Client` row is missing — **before** calling `provider.create_charge`. This is a deliberate, small `PixService` business-rule change (not Efí-specific — the rule is "a Pix charge needs a payer"), and it applies to `fake` too: today the fake demo *can* Pix-pay a clientless proposal (the fake provider ignores `payer` entirely); after this change it can't. Accepted as correct — a clientless proposal reaching a real "Pagar com Pix" click is itself a data-quality smell worth surfacing rather than silently charging with no payer.

**c) Date-based `create_charge` signature (replaces duration-based).** The original draft kept `expires_in: int` (seconds from creation) to match Cob/the fake provider's TTL shape. CobV is calendar-anchored — there is no "duration from creation" concept to express. New signature:

```python
async def create_charge(
    self,
    txid: str,
    amount: Decimal,
    due_date: date,           # → calendario.dataDeVencimento
    validity_days: int,       # → calendario.validadeAposVencimento
    description: str,
    payer: PayerInfo | None,
) -> PixChargeData
```

`expires_in: int` is removed entirely — not deprecated, not made optional. `InMemoryFakePixProvider` updates its signature to match (its own internal TTL bookkeeping, if any, becomes calendar-based too — it's a test convenience, not something a real PSP mirrors literally). `PixChargeData.expires_at` keeps its existing shape (a `datetime`); only what populates it changes.

**d) Webhook query params.** Unchanged from the original design. Efí does not HMAC-sign the body. Their mechanism: a static token embedded in the *registered callback URL's query string* (`?hmac=<token>&ignorar=`); the receiver validates incoming requests carry the same token — a "shared secret in callback URL" pattern other PSPs also use. `verify_webhook` gains a `query_params` parameter:

```python
def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent
```

Cascades to: `PixService.handle_webhook(headers, query_params, body)`, `api/webhooks.py` (passes `dict(request.query_params)`), and `InMemoryFakePixProvider.verify_webhook` (accepts the new param, ignores it, keeps its own HMAC-over-body scheme — that's a test convenience, not something a real PSP does).

**No protocol change needed** for the missing `status` field: Efí's real webhook payload (`{"pix": [{"endToEndId", "txid", "chave", "valor", "horario", "infoPagador"}]}`) carries no status — receiving a `pix[]` entry *is* the "received/paid" signal. `EfiPixProvider.verify_webhook` constructs `WebhookEvent(status="paid", txid=entry["txid"], paid_amount=Decimal(entry["valor"]), ...)` directly. `WebhookEvent.status` stays a generic string; the Protocol is unaffected.

### 3. Unified charge lifecycle — one shared idempotent core, two thin entry points

This is the heart of the redesign: **one CobV charge per `parcela`, ever**, regardless of how many times "Pagar com Pix" gets clicked, and regardless of whether the eventual trigger is a customer or (once Phase 2 lands) a cron. The "create-or-reuse" logic is identical no matter who's asking — it collapses into one private helper that both public entry points share:

```python
async def _ensure_charge(self, parcela: ParcelaPayment) -> PixCharge:
    # idempotent reuse check (existing parcela.last_pix_charge_id, lazy-flip-expired)
    # PayerInfo construction (§2a — Client.tipo/cpf_cnpj → document_type/document)
    # provider.create_charge(txid=, amount=parcela.valor_parcela,
    #                        due_date=parcela.vencimento, validity_days=<from BusinessRule, see 3a>,
    #                        description=..., payer=...)
    # QR PNG generation + storage upload
    # PixCharge persistence
```

Two thin public methods wrap it, differing only in the two things that genuinely depend on *who's calling*:

- **`create_charge_for_parcela(parcela_payment_id, ctx)`** — customer/staff-facing. Verifies ownership (`ctx.client_id` check, `service.py:53-57`), and on a *freshly created* charge (not on idempotent reuse — the existing early-return at `service.py:62-70` already returns before reaching the notification block, so this distinction is preserved with zero extra code) sends the `pix_link` notification, exactly as today.
- **A system-trigger variant (Phase 2 names and wires this — see its spec)** — no `RequestContext`, no ownership check (the cron is trusted: it already filters by tenant and skips clientless proposals at the query level), no `pix_link` notification (Phase 2 folds the `brcode` into the due-soon reminder email instead — sending both would double-notify about the same charge).

Notice what's *gone* relative to the pre-redesign sketch: there's no `expires_in` parameter to thread through anymore, because every charge's validity is derived identically regardless of trigger (§3a/§3b). The shared core is *simpler* under CobV than it would have been stretching Cob across days — not just architecturally cleaner.

**3a — Validity window: one new `BusinessRule`, not a hardcoded constant.** `calendario.validadeAposVencimento` needs a value — "how many days past `vencimento` should this charge remain payable?" New tenant-wide key in `_RULE_DEFAULTS` (`rules_service.py`), following the established `chave`/`valor_json`/`descricao` convention:

```python
"pix_validade_apos_vencimento_dias": (60, "Dias de validade do Pix após o vencimento da parcela"),
```

**Why 60:** generous enough to cover realistic late-payer behavior in CDC/CCB vehicle financing (this is not subscription billing — a customer 30-45 days late paying their original parcela via the original Pix is normal), short enough that a customer 60+ days out is already FASE 3/4 (Inadimplência/Renegociação) territory, where the *original* charge arguably ought to be superseded by a renegotiated one rather than kept alive indefinitely. 30/60/90-day windows are conventional for boleto/Pix-vencimento in Brazil — 60 sits squarely in the normal range, and is trivially tenant-adjustable via the admin business-rules UI (same convention as `rateio_ipva_meses_default` etc. — needs the same seed-migration treatment Phase 2 will add for its own new keys, see that spec's §1).

**3b — `expires_at` derivation (BRT-anchored).** `calendario.dataDeVencimento + validadeAposVencimento` lands on a future calendar date; "expires_at" means "end of that day, in the timezone the business and the customer actually think in":

```python
BRT = ZoneInfo("America/Sao_Paulo")
valid_through = parcela.vencimento + timedelta(days=validity_days)
expires_at_utc = datetime.combine(valid_through, time(23, 59, 59), tzinfo=BRT).astimezone(UTC)
```

`vencimento` is a naive `Date` the business (and the customer reading "vence em {{ vencimento }}") thinks of in Brazilian local time — anchoring in UTC would expire the charge three hours before the calendar day the customer was told it actually ends, rejecting an on-time-by-the-customer's-clock payment. `zoneinfo.ZoneInfo` (stdlib) over a hardcoded UTC-3 offset, in case Brazil's DST policy ever changes again. **`PixCharge.expires_at` keeps its existing column (`DateTime(timezone=True)`, `models.py:659`) — zero schema change; only the value populating it changes.** `_lazy_flip_expired` (`service.py:36-42`) needs no changes — it already just compares `expires_at` to "now."

**Idempotent reuse, unchanged contract.** If an existing pending (non-expired) charge already covers the parcela — including one created by the *other* trigger (e.g., the cron generated one proactively, customer clicks "Pagar com Pix" before paying it) — the shared reuse path returns it unchanged. No duplicate charge, no duplicate provider call, no special-casing which trigger created it.

### 4. Webhook validation strategy (skip-mTLS)

Unchanged from the original design — entirely independent of Cob vs. CobV (Efí validates webhook authenticity per registered `chave`, not per charge type).

Efí supports two validation modes:

- **mTLS** (their default recommendation): requires the web server/reverse-proxy to perform mutual-TLS handshakes with Efí's client certificate chain — infrastructure-level work (nginx/traefik config), out of place for a backend-code "Phase 1 básico" change.
- **Skip-mTLS**: register the webhook with `x-skip-mtls-checking: true`; the integrator is responsible for validating the callback's authenticity. Efí's own guidance suggests combining a static URL token with their fixed sender IP (`34.193.116.226`) — but **this codebase has no `request.client`/`X-Forwarded-For` handling anywhere** (verified via grep). Behind a reverse proxy (the `ops/docker-compose.yml` setup likely runs one — note the `Caddyfile` mount), `request.client.host` would be the *proxy's* IP, not Efí's; trusting `X-Forwarded-For` without proxy-level config would make the check spoofable. Implementing it now would either always-fail or be a check that doesn't actually check anything.

**Decision: skip-mTLS, hmac-token only — no IP allowlist in Phase 1.** `EfiPixProvider.verify_webhook` checks `query_params.get("hmac") == settings.pix_webhook_secret` (constant-time compare via `hmac.compare_digest`). The token *is* the real security boundary here (a secret Efí must echo back verbatim); the IP check is defense-in-depth that needs infrastructure this project doesn't have configured yet. This reuses the existing `PIX_WEBHOOK_SECRET` setting (already present from Phase 6) with no schema change. **Both the IP allowlist and mTLS are documented as hardening items for a later phase**, bundled together since both depend on proxy/cert-handling infrastructure (see Out of scope).

### 5. New settings (`settings.py`)

Unchanged from the original design:

```python
efi_client_id: str = ""
efi_client_secret: str = ""
efi_certificate_path: str = ""   # absolute path to .pem on disk (inside the container — see runbook §ops)
efi_pix_key: str = ""            # the recipient's registered Pix key (UUID format)
efi_sandbox: bool = True
```

**Selector rename: `pix_provider` values become `fake | efi`** (was `fake | external`). Renaming now — while `EfiPixProvider` is the only real provider and zero deployed `.env` files depend on the old value — avoids a breaking rename later when a second real PSP exists and `"external"` stops meaning anything specific. `EfiPixProvider.name = "efi"` to match. Cascading edits (both confirmed via grep — no other references exist):

- `deps.get_pix_provider`: `if settings.pix_provider == "efi": return EfiPixProvider(settings)`, replacing the `StubExternalPixProvider` branch (which is deleted — its sole purpose, a placeholder for "real PSP wiring," is now fulfilled; no test references it).

**Cached singleton for the `efi` branch.** All four call sites (`webhooks.py`, `portal.py`, `proposals.py`, `pix_admin.py` — confirmed via grep) call `get_pix_provider(settings)` fresh per-request; harmless for `fake`/`stub` (cheap to construct, no I/O), but `EfiPixProvider.__init__` builds an `EfiPay({...})` client that reads the cert from disk and (per Efí's OAuth2 model) authenticates with Efí's token endpoint — doing that on *every* charge creation, cancel, admin check, and incoming webhook delivery multiplies auth calls and risks throttling on a real PSP's auth endpoint. This is a new pattern for the codebase (no existing dep — `get_settings`, `get_storage_backend` — caches today), kept minimal and scoped to the `efi` branch only: a module-level `_efi_provider: EfiPixProvider | None = None` in `pix/deps.py`, lazily constructed once and reused (not `lru_cache` on `get_pix_provider` itself, since that would also wrongly cache `fake`/`stub` across settings changes in tests). `fake`/`stub` branches stay exactly as today — constructed fresh, no caching.

- `pix_admin.py:41` mark-paid gate: `if settings.pix_provider == "external"` → **`if settings.pix_provider != "fake"`**. Semantically exact ("block the demo button whenever a real provider is active") and stays correct automatically if a third provider is ever added — no more naming-debt in this file.

**Startup guards (in `deps.get_pix_provider` or app startup), both fail fast rather than at the worst possible moment:**

- When `pix_provider == "efi"`: validate `efi_client_id`, `efi_client_secret`, `efi_certificate_path` (and `Path(efi_certificate_path).exists()`), and `efi_pix_key` are all non-empty — raise immediately if not. Otherwise the app boots fine and the *first customer* to click "Pagar com Pix" in production gets a raw 500.
- When `app_env == "production"` and `efi_sandbox == True`: log a loud `loguru` warning at startup. This combination is almost certainly a misconfiguration (charges silently land in the sandbox; customers think they paid; nothing shows up in the real account) and would be brutal to debug after the fact. A warning (not a hard stop) avoids blocking a legitimate staged-rollout scenario.

### 6. CLI command: `pix register-webhook`

Unchanged from the original design — one-time setup action, registers the callback URL with Efí (`PUT /v2/webhook/:chave`, `webhookUrl: "https://<frontend_base_url>/api/v1/webhooks/pix?hmac=<PIX_WEBHOOK_SECRET>&ignorar="`, **header `x-skip-mtls-checking: true`** — required on this call per Efí's docs to register skip-mTLS mode matching §4's decision; omitting it risks Efí defaulting to mTLS validation, which the Caddy proxy can't satisfy, silently breaking webhook delivery in production). Implemented as a `typer` sub-app alongside the existing CLI structure (`cli/main.py` already composes `tenant_app`/`user_app`/`db_app`/`notifications_app` via `app.add_typer(...)` — a `pix_app` follows the same shape), reusable whenever the domain or secret changes (env migration, rotation). Idempotent — re-running overwrites the registration with the current URL/secret (`PUT` semantics).

### 7. Setup runbook (new doc: `docs/agents/efi-pix-setup.md` or similar)

Step-by-step guide covering:

1. Creating an Efí sandbox ("homologação") account and registering a Pix key.
2. Generating + downloading the `.p12` certificate and converting it to `.pem` via `openssl pkcs12 -in certificado.p12 -out certificado.pem -nodes -password pass:""` (confirmed exact command from Efí's own docs).
3. **Docker volume mount for the cert** — `EFI_CERTIFICATE_PATH` is useless if the container can't see the file at that path. `ops/docker-compose.yml`'s `worker`/`api` services already follow this pattern for on-disk files (`PDF_OUTPUT_DIR: /var/lib/finacialsim/pdfs` paired with `volumes: pdf-store:/var/lib/finacialsim/pdfs`); the runbook documents bind-mounting the converted `.pem` the same way (e.g. into `/var/lib/finacialsim/certs/efi.pem`) and pointing `EFI_CERTIFICATE_PATH` at the in-container path.
4. Populating `.env` (`EFI_CLIENT_ID`, `EFI_CLIENT_SECRET`, `EFI_CERTIFICATE_PATH`, `EFI_PIX_KEY`, `EFI_SANDBOX=true`, `PIX_PROVIDER=efi`).
5. Running `pix register-webhook`.
6. **Webhook delivery verification (explicit troubleshooting step — not just "hope it works"):** the `?hmac=...&ignorar=` URL mechanism that prevents Efí from appending `/pix` to the registered URL is sourced from a community forum post, not Efí's official webhook docs — if it behaves differently than described, the webhook silently 404s (Efí retries up to 9 times, then gives up, and "payment confirmation just doesn't happen" is brutal to debug post-launch). After registration, Efí sends an automatic test notification — check **Efí's dashboard delivery log** for the actual URL/path they called, and adjust the registered URL (with/without `/pix`, with/without `?ignorar=`) if it doesn't match `/api/v1/webhooks/pix`. Turns an uncertain assumption into a verify-and-correct loop instead of a silent failure mode.
7. **Manual smoke-test checklist (CobV-shaped — note the changes from a Cob-based test plan):** create a sandbox CobV charge for a parcela due a few days out, confirm the same `brcode`/QR remains payable (a) before `vencimento`, (b) on `vencimento`, and (c) a few days after — the long-lived single-charge model means all three matter, not just "does it work once." Pay it via Efí's sandbox simulator. **Explicitly test a payment for a value above R$ 10** and confirm the webhook still fires and `parcela` flips to `paid` — this directly verifies (or refutes) the "R$0.01–10.00 only" claim flagged in §1 before it can bite a real tenant. (Sandbox charges ≤ R$10.01 are documented to auto-confirm without a manual simulator step — useful for a quick first pass, but the above-R$10 webhook check is the one that actually matters for production confidence.)

### Tests

- `EfiPixProvider`: mock the `EfiPay` client at the boundary (inject a stub/`MagicMock` client), assert request payload shape (`devedor`, `valor.original`, `calendario.dataDeVencimento`, `calendario.validadeAposVencimento`, explicit-zero `juros`/`multa`, `chave`) and correct mapping of the SDK response into `PixChargeData` (brcode, decoded QR PNG bytes, `expires_at` derived BRT-anchored from `dataDeVencimento + validadeAposVencimento`).
- `cancel_charge`: asserts `PATCH .../cobv/:txid` payload shape (exact status string per the verified SDK example); provider exception is swallowed (matches existing `cancel_charges_for_proposal` contract).
- `verify_webhook`: matching `hmac` query param → valid; mismatched/missing → raises; real-shaped Efí payload (`{"pix": [{"txid", "valor", "horario", ...}]}`, no `status` field, identical regardless of Cob/CobV origin) → `WebhookEvent(status="paid", paid_amount=Decimal(...))`.
- `PixService._ensure_charge` (shared core): asserts `PayerInfo` is correctly built from the `Client` (`document_type` from `Client.tipo`, digits-only `document` stripped from `cpf_cnpj`); asserts `due_date`/`validity_days` threaded correctly from `parcela.vencimento`/the new `pix_validade_apos_vencimento_dias` rule; asserts idempotent reuse returns the existing pending charge with no duplicate provider call **regardless of which entry point originally created it**; asserts `ValidationError` is raised when `sim.client_id is None` (§2b guard), for both `fake` and `efi` providers.
- `create_charge_for_parcela` (customer entry point): ownership check; `pix_link` notification fires on fresh creation, not on idempotent reuse (regression-pins the existing `service.py:62-70` early-return behavior).
- `pix register-webhook` CLI: asserts the registered URL is built correctly from `frontend_base_url` + `pix_webhook_secret`.
- Real sandbox round-trip (actual cert + creds) is a **manual** verification step in the runbook — not part of automated CI, since it requires a live Efí sandbox account.

## Out of scope

- mTLS webhook validation **and** IP allowlisting (bundled — both depend on infrastructure this project doesn't have configured: reverse-proxy mutual-TLS termination and trusted `X-Forwarded-For`/`request.client` handling, neither of which exist anywhere in the codebase today per grep. Documented as a future hardening item once that infra exists).
- **Juros/multa policy** — actual interest/penalty *rates*, grace periods (`carência`), and accrual rules. This phase wires the CobV plumbing with explicit-zero values (§1b) so FASE 3 (Inadimplência) only has to populate real `BusinessRule`-driven rates — it does not design that policy.
- **Desconto/abatimento** (renegotiation discounts/rebates) — FASE 4 (Renegociação) territory; the fields are omitted from the request body entirely in this phase.
- Pix Automático, scheduled/recurring Pix (a distinct Efí product from CobV — not what "cobrança automática" means in this codebase's roadmap, which is "the system proactively *generates and sends* a regular Pix charge ahead of time," not Efí's recurring-debit product).
- Per-tenant Efí accounts (this is a single platform-wide account/cert, matching how the rest of the SaaS centralizes PSP credentials).
- Refund/devolução flows.
- DB schema and frontend changes — Phase 6-complete, stays as-is. (The CobV redesign changes *what populates* `PixCharge.expires_at`, not its column type — confirmed zero migration needed.)
- Any `PixService`/`fake`-provider changes beyond the ones enumerated in this doc: (a) `PayerInfo`/`query_params`/date-based-signature threading (§2), (b) the clientless-proposal guard (§2b), and (c) collapsing charge creation into the shared `_ensure_charge` core (§3, which deliberately *does* change the fake demo's TTL-expiry behavior — see the next bullet). No other `PixService` business logic shifts.
- **The fake-provider demo's 30-minute TTL goes away** — `InMemoryFakePixProvider` adopts the same calendar-anchored validity model (its TTL becomes "valid through `vencimento + validadeAposVencimento`," matching the real provider's contract, since `PixProvider` no longer has an `expires_in` concept to fake). This is a deliberate, visible behavior change to the demo flow — flagged here so it isn't mistaken for an oversight.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Skip-mTLS leaves webhook authenticity resting on a single shared secret in a URL | The token is a real secret Efí must echo back verbatim — it *is* the security boundary, not a weak stand-in. IP allowlist + mTLS documented as layered hardening once proxy infra exists |
| Sync SDK blocks the event loop | Wrap every SDK call in `asyncio.to_thread`, matching `workers/tasks.py` / `storage/s3.py` convention |
| Cert file missing/misconfigured, or other `efi_*` settings empty | Eager startup validation (non-empty + `Path.exists()` on cert) raises immediately when `pix_provider == "efi"` — fails at boot, not on the first customer's payment attempt |
| `app_env=production` + `efi_sandbox=true` (near-certain misconfiguration: charges silently land in sandbox) | Loud `loguru` warning at startup on this combination |
| **Unverified claim that CobV webhooks may not fire for charges above R$10 in some environment** — if true for production, reconciliation breaks silently for every typical-value parcela | Explicit above-R$10 webhook-delivery check folded into the runbook's manual smoke test (§7, step 7) — must pass before any real tenant goes live on `efi`. If it *does* turn out to be a real production constraint (vs. a misattributed sandbox quirk), that's a launch-blocking finding requiring its own design conversation, not a corner to round off |
| A future reader sees `juros`/`multa` sent as explicit zero on every charge and wonders whether late payments silently go unpenalized by mistake | They do — deliberately, for now (§1b, "Out of scope"). Documented inline at the point of construction (not just in this spec) so FASE 3's eventual non-zero values read as "turning on a designed knob," not "fixing an oversight" |
| Orphaned real Efí charge if DB commit fails *after* a successful `provider.create_charge` call (pre-existing scaffold ordering in `service.py:72-104` — harmless for the fake provider, but now has a real external side effect) | Accepted as a documented known-risk: small blast radius (a few stray low-value charges, caught on reconciliation); fixing requires touching `PixService` internals, which this phase deliberately keeps minimal. Flagged here as a follow-up: persist the `PixCharge` row in a `creating` state *before* calling the provider |
| Efí sandbox payload / webhook-URL routing drifts from documented (and community-sourced) examples | `verify_webhook` parsing isolated to `efi.py`, tests pin the expected shape; runbook's explicit "verify delivery URL against Efí's dashboard log" step catches routing drift before it becomes a silent production failure |
| Raw SDK/network exceptions surfacing as unhelpful 500s on transient PSP failures | `EfiPixProvider` translates them to `ValidationError` at the boundary — caught by the existing `AppError` handler, contained entirely in `efi.py` |
| `PayerInfo`/`query_params`/date-signature Protocol changes ripple through fake provider + service + webhook endpoint | All call sites enumerated above; changes are mechanical signature threading, covered by existing test suite plus new assertions |

## Acceptance checklist

- [ ] `PIX_PROVIDER=efi` with valid Efí sandbox credentials creates a real CobV charge anchored to `parcela.vencimento`; `brcode` + QR PNG returned to the customer portal exactly as the fake flow does.
- [ ] The same charge — same `brcode`, same QR — remains payable across at least three points in time relative to `vencimento`: a few days before, on the day, and a few days after (manually verified per the runbook's smoke test, §7 step 7).
- [ ] `PayerInfo` correctly built from `Client.cpf_cnpj`/`Client.tipo`/`Client.nome` (digits-only document, explicit `document_type` from `tipo`, not digit-count guessing) and reaches Efí's `devedor` field.
- [ ] Paying the sandbox charge — **including a payment above R$ 10** — triggers Efí's webhook; `verify_webhook` validates the `hmac` query token, parcela flips to `paid`, audit + webhook-event rows created — mirroring the fake-provider flow's guarantees.
- [ ] Invalid/missing `hmac` token → webhook returns 200, `signature_valid=false`, no state change (same contract as today).
- [ ] Canceling a proposal cancels its pending Efí charges via `PATCH .../cobv/:txid`.
- [ ] `pix register-webhook` registers the correct URL; delivery verified against Efí's dashboard log and corrected if it doesn't match `/api/v1/webhooks/pix`.
- [ ] App refuses to boot with `PIX_PROVIDER=efi` and missing/empty `efi_*` settings or a missing cert file; logs a loud warning on `app_env=production` + `efi_sandbox=true`.
- [ ] `StubExternalPixProvider` removed; `pix_admin.py` gate updated to `!= "fake"`; `fake`/`InMemoryFakePixProvider` adopts the same calendar-anchored validity contract (no more 30-min TTL) and its demo flow remains otherwise unaffected.
- [ ] Transient Efí/SDK failures surface as a clean `ValidationError` message to the customer, not a raw 500.
- [ ] Setup runbook (incl. cert Docker volume mount and the above-R$10 webhook verification step) walks a fresh operator from zero to a working sandbox integration, end to end.
- [ ] `pix_validade_apos_vencimento_dias` (default 60) appears in `_RULE_DEFAULTS`, is editable per-tenant via the admin business-rules UI, and correctly drives `calendario.validadeAposVencimento` end to end.
