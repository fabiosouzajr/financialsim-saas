# Efí Pix Provider — Phase 1 (PIX básico real)

> Implements the real PSP wiring that Phase 6 deferred: a working `EfiPixProvider` behind the existing `PixProvider` Protocol, replacing `StubExternalPixProvider`. Touches `PixService` only for the mechanical `PayerInfo`/`query_params` threading this requires, plus one small deliberate guard (§2a — a clientless proposal can't be Pix-charged, applies to `fake` too). No DB schema or frontend changes; the fake-provider demo is otherwise unaffected.
>
> **Predecessor:** Phase 6 — Portal do cliente + Pix scaffold (`2026-05-28-saas-phase-6-portal-cliente-pix.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md` — "FASE 1 — PIX básico"

## Goal

`PIX_PROVIDER=efi` produces real PIX charges through Efí (Bank): create an immediate charge, generate a QR code + copia-e-cola, receive payment confirmation via webhook, cancel a charge. End-to-end demo: staff/customer triggers "Pagar com Pix" → real Efí sandbox charge created → customer pays via Efí's sandbox simulator → webhook confirms → `parcela` flips to `paid`, exactly as the fake-provider flow does today.

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
| `create_charge` | `efi.pix_create_charge(params={"txid": txid}, body=body)` → `PUT /v2/cob/:txid`, then `efi.pix_generate_qrcode(params={"id": loc_id})` → `GET /v2/loc/:id/qrcode` | Builds `devedor` from `payer.document`/`payer.document_type` (`{"cpf": ...}` or `{"cnpj": ...}`); `valor.original` from `amount`; `chave` from settings; `calendario.expiracao` from `expires_in`. Response gives `pixCopiaECola` (→ `brcode`) and `loc.id`; second call returns `imagemQrcode` — a base64 PNG with a `data:image/png;base64,` prefix that must be stripped before decoding into `qr_png_bytes`. Maps Efí's `calendario.criacao + expiracao` to `expires_at`. SDK/network exceptions are caught here and re-raised as `ValidationError("Não foi possível gerar o PIX no momento, tente novamente")` — see §7 (Error translation). |
| `cancel_charge` | `efi.pix_update_charge(params={"txid": txid}, body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"})` → `PATCH /v2/cob/:txid` | Errors logged and swallowed — `PixService.cancel_charges_for_proposal` already treats provider cancel failures as best-effort (`service.py:319-322`). |
| `verify_webhook` | — (local validation only) | See §3 below: static token in the callback URL's query string, NOT body HMAC. Synthesizes `WebhookEvent(status="paid", ...)` from Efí's real payload shape, which carries no explicit status field. |

**SDK method names — verified directly against `efipay/sdk-python-apis-efi`'s own example files (not a placeholder anymore):**

- **`pix_create_charge(params={"txid": txid}, body=body)`** is the txid-based call (`PUT /v2/cob/:txid`) — **not** `pix_create_immediate_charge`. That name is misleading: `pix_create_immediate_charge(body=body)` takes *no* `params`/`txid` — it's the `POST /v2/cob` variant where Efí generates the txid server-side. Using it would return a different txid than the one `PixService.create_charge_for_parcela` generates locally (`service.py:73-74`) and stores on `PixCharge.txid`, breaking the webhook lookup `select(PixCharge).where(PixCharge.txid == event.txid)` (`service.py:182-185`). `EfiPixProvider` MUST call `pix_create_charge`, passing the locally-generated `txid` through `params`.
- **`pix_generate_qrcode(params={"id": loc_id})`** fetches the QR — confirmed via `examples/pix/location/loc/pix_generate_qrcode.py`. Response key is `imagemQrcode` (not a generic "base64 QR PNG" — it's prefixed `data:image/png;base64,...`).
- **`pix_update_charge(params={"txid": txid}, body=...)`** is `PATCH /v2/cob/:txid` — confirmed via `examples/pix/cob/pix_update_charge.py`. Used for `cancel_charge` with `body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}`.

### 7. Error translation at the provider boundary

`create_charge_for_parcela` calls `provider.create_charge(...)` with no try/except (`service.py:76`) — fine for the fake provider (can't realistically fail), not fine for a real PSP that will occasionally hit network blips, Efí downtime, auth/cert issues, or payer-data validation rejections. Left untranslated, these surface as raw 500s (FastAPI's default handler — `main.py` only registers a handler for the app's own `AppError` hierarchy). `EfiPixProvider` catches SDK/`httpx`-level exceptions internally and re-raises as `ValidationError` with a user-facing PT-BR message, so the existing `AppError` handler formats them cleanly — entirely contained in `efi.py`, no `PixService` changes.

### 2. `PixProvider` Protocol changes (`pix/protocol.py`)

Two gaps in the current scaffold surfaced by Efí's real API. Both are generic PIX-PSP concepts (not Efí-specific), so fixing them keeps the interface pluggable for any future provider:

**a) Structured payer identity.** Efí requires `devedor: {cpf, nome}` or `{cnpj, nome}` — distinct fields per document type, not a generic blob. The current `payer: str` (always passed as `""` — a placeholder never wired to real data, `service.py:81`) can't carry that. New dataclass, mirroring the existing `PixChargeData`/`WebhookEvent` convention:

```python
@dataclass
class PayerInfo:
    document: str          # CPF or CNPJ, digits only (punctuation stripped)
    document_type: Literal["cpf", "cnpj"]
    name: str
```

**Type comes from `Client.tipo` (already `pf`/`pj`, `models.py:380-382`), not from sniffing digit-count** — `Client.cpf_cnpj` is stored as-entered with punctuation (`client_service.py:108` does no normalization: `123.456.789-09` / `12.345.678/0001-90`), so length-based guessing would be both wrong (wrong length pre-strip) and fragile (malformed data could produce a misleading length post-strip). `create_charge`'s `payer: str` becomes `payer: PayerInfo | None`. `PixService.create_charge_for_parcela` looks up the `Client` (via `Proposal → Simulation → Client`), strips non-digits from `cpf_cnpj`, maps `tipo.pf → "cpf"` / `tipo.pj → "cnpj"`, and passes `PayerInfo(document=..., document_type=..., name=client.nome)`.

**New guard — clientless proposal can't be Pix-charged.** `Simulation.client_id` is nullable (`models.py:273-275`); `proposal_service.py:89` already shows `Proposal`s can exist with no linked `Client` (`client = ... if sim.client_id else None`). Staff (not just customers) can reach `create_charge_for_parcela` for such a proposal's parcelas — the customer-ownership check only applies `if ctx.client_id is not None`. Rather than thread `payer=None` through to a real PSP (Efí's `devedor` is technically optional, but a Pix charge with no payer binding is a real gap for reconciliation/compliance), `create_charge_for_parcela` now raises `ValidationError("não é possível gerar Pix sem cliente vinculado à proposta")` when `sim.client_id is None` or the `Client` row is missing — **before** calling `provider.create_charge`. This is a deliberate, small `PixService` business-rule change (not Efí-specific — the rule is "a Pix charge needs a payer"), and it applies to `fake` too: today the fake demo *can* Pix-pay a clientless proposal (the fake provider ignores `payer` entirely); after this change it can't. Accepted as correct — a clientless proposal reaching a real "Pagar com Pix" click is itself a data-quality smell worth surfacing rather than silently charging with no payer.

**b) Webhook query params.** Efí does not HMAC-sign the body. Their mechanism: a static token embedded in the *registered callback URL's query string* (`?hmac=<token>&ignorar=`); the receiver validates incoming requests carry the same token — a "shared secret in callback URL" pattern other PSPs also use. `verify_webhook` gains a `query_params` parameter:

```python
def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent
```

Cascades to: `PixService.handle_webhook(headers, query_params, body)`, `api/webhooks.py` (passes `dict(request.query_params)`), and `InMemoryFakePixProvider.verify_webhook` (accepts the new param, ignores it, keeps its own HMAC-over-body scheme — that's a test convenience, not something a real PSP does).

**No protocol change needed** for the missing `status` field: Efí's real webhook payload (`{"pix": [{"endToEndId", "txid", "chave", "valor", "horario", "infoPagador"}]}`) carries no status — receiving a `pix[]` entry *is* the "received/paid" signal. `EfiPixProvider.verify_webhook` constructs `WebhookEvent(status="paid", txid=entry["txid"], paid_amount=Decimal(entry["valor"]), ...)` directly. `WebhookEvent.status` stays a generic string; the Protocol is unaffected.

### 3. Webhook validation strategy (skip-mTLS)

Efí supports two validation modes:
- **mTLS** (their default recommendation): requires the web server/reverse-proxy to perform mutual-TLS handshakes with Efí's client certificate chain — infrastructure-level work (nginx/traefik config), out of place for a backend-code "Phase 1 básico" change.
- **Skip-mTLS**: register the webhook with `x-skip-mtls-checking: true`; the integrator is responsible for validating the callback's authenticity. Efí's own guidance suggests combining a static URL token with their fixed sender IP (`34.193.116.226`) — but **this codebase has no `request.client`/`X-Forwarded-For` handling anywhere** (verified via grep). Behind a reverse proxy (the `ops/docker-compose.yml` setup likely runs one — note the `Caddyfile` mount), `request.client.host` would be the *proxy's* IP, not Efí's; trusting `X-Forwarded-For` without proxy-level config would make the check spoofable. Implementing it now would either always-fail or be a check that doesn't actually check anything.

**Decision: skip-mTLS, hmac-token only — no IP allowlist in Phase 1.** `EfiPixProvider.verify_webhook` checks `query_params.get("hmac") == settings.pix_webhook_secret` (constant-time compare via `hmac.compare_digest`). The token *is* the real security boundary here (a secret Efí must echo back verbatim); the IP check is defense-in-depth that needs infrastructure this project doesn't have configured yet. This reuses the existing `PIX_WEBHOOK_SECRET` setting (already present from Phase 6) with no schema change. **Both the IP allowlist and mTLS are documented as hardening items for a later phase**, bundled together since both depend on proxy/cert-handling infrastructure (see Out of scope).

### 4. New settings (`settings.py`)

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

### 5. CLI command: `pix register-webhook`

One-time setup action — registers the callback URL with Efí (`PUT /v2/webhook/:chave`, `webhookUrl: "https://<frontend_base_url>/api/v1/webhooks/pix?hmac=<PIX_WEBHOOK_SECRET>&ignorar="`, **header `x-skip-mtls-checking: true`** — required on this call per Efí's docs to register skip-mTLS mode matching §3's decision; omitting it risks Efí defaulting to mTLS validation, which the Caddy proxy can't satisfy, silently breaking webhook delivery in production). Implemented as a `typer` sub-app alongside the existing CLI structure (`cli/main.py` already composes `tenant_app`/`user_app`/`db_app`/`notifications_app` via `app.add_typer(...)` — a `pix_app` follows the same shape), reusable whenever the domain or secret changes (env migration, rotation). Idempotent — re-running overwrites the registration with the current URL/secret (`PUT` semantics).

### 6. Setup runbook (new doc: `docs/agents/efi-pix-setup.md` or similar)

Step-by-step guide covering:

1. Creating an Efí sandbox ("homologação") account and registering a Pix key.
2. Generating + downloading the `.p12` certificate and converting it to `.pem` via `openssl pkcs12 -in certificado.p12 -out certificado.pem -nodes -password pass:""` (confirmed exact command from Efí's own docs).
3. **Docker volume mount for the cert** — `EFI_CERTIFICATE_PATH` is useless if the container can't see the file at that path. `ops/docker-compose.yml`'s `worker`/`api` services already follow this pattern for on-disk files (`PDF_OUTPUT_DIR: /var/lib/finacialsim/pdfs` paired with `volumes: pdf-store:/var/lib/finacialsim/pdfs`); the runbook documents bind-mounting the converted `.pem` the same way (e.g. into `/var/lib/finacialsim/certs/efi.pem`) and pointing `EFI_CERTIFICATE_PATH` at the in-container path.
4. Populating `.env` (`EFI_CLIENT_ID`, `EFI_CLIENT_SECRET`, `EFI_CERTIFICATE_PATH`, `EFI_PIX_KEY`, `EFI_SANDBOX=true`, `PIX_PROVIDER=efi`).
5. Running `pix register-webhook`.
6. **Webhook delivery verification (explicit troubleshooting step — not just "hope it works"):** the `?hmac=...&ignorar=` URL mechanism that prevents Efí from appending `/pix` to the registered URL is sourced from a community forum post, not Efí's official webhook docs — if it behaves differently than described, the webhook silently 404s (Efí retries up to 9 times, then gives up, and "payment confirmation just doesn't happen" is brutal to debug post-launch). After registration, Efí sends an automatic test notification — check **Efí's dashboard delivery log** for the actual URL/path they called, and adjust the registered URL (with/without `/pix`, with/without `?ignorar=`) if it doesn't match `/api/v1/webhooks/pix`. Turns an uncertain assumption into a verify-and-correct loop instead of a silent failure mode.
7. Manual smoke-test checklist: create a sandbox charge, pay it via Efí's sandbox simulator (note: sandbox charges ≤ R$10.01 auto-confirm), confirm webhook flips `parcela` to `paid`.

### Tests

- `EfiPixProvider`: mock the `EfiPay` client at the boundary (inject a stub/`MagicMock` client), assert request payload shape (`devedor`, `valor.original`, `chave`, `calendario.expiracao`) and correct mapping of the SDK response into `PixChargeData` (brcode, decoded QR PNG bytes, `expires_at`).
- `cancel_charge`: asserts `PATCH` payload `{"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}`; provider exception is swallowed (matches existing `cancel_charges_for_proposal` contract).
- `verify_webhook`: matching `hmac` query param → valid; mismatched/missing → raises; real-shaped Efí payload (`{"pix": [{"txid", "valor", "horario", ...}]}`, no `status` field) → `WebhookEvent(status="paid", paid_amount=Decimal(...))`.
- `PixService.create_charge_for_parcela`: asserts `PayerInfo` is correctly built from the `Client` (`document_type` from `Client.tipo`, digits-only `document` stripped from `cpf_cnpj`) and threaded through to `provider.create_charge`; asserts `ValidationError` is raised when `sim.client_id is None` (§2a guard), for both `fake` and `efi` providers.
- `pix register-webhook` CLI: asserts the registered URL is built correctly from `frontend_base_url` + `pix_webhook_secret`.
- Real sandbox round-trip (actual cert + creds) is a **manual** verification step in the runbook — not part of automated CI, since it requires a live Efí sandbox account.

## Out of scope

- mTLS webhook validation **and** IP allowlisting (bundled — both depend on infrastructure this project doesn't have configured: reverse-proxy mutual-TLS termination and trusted `X-Forwarded-For`/`request.client` handling, neither of which exist anywhere in the codebase today per grep. Documented as a future hardening item once that infra exists).
- Pix Automático, scheduled/recurring Pix.
- Per-tenant Efí accounts (this is a single platform-wide account/cert, matching how the rest of the SaaS centralizes PSP credentials).
- Refund/devolução flows.
- DB schema and frontend changes — Phase 6-complete, stays as-is.
- Any `PixService`/`fake`-provider changes beyond the two enumerated in this doc: (a) mechanical `PayerInfo`/`query_params` threading (§2), and (b) the clientless-proposal guard (§2a, which deliberately *does* change `fake`'s demo behavior — see rationale there). No other `PixService` business logic shifts.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Skip-mTLS leaves webhook authenticity resting on a single shared secret in a URL | The token is a real secret Efí must echo back verbatim — it *is* the security boundary, not a weak stand-in. IP allowlist + mTLS documented as layered hardening once proxy infra exists |
| Sync SDK blocks the event loop | Wrap every SDK call in `asyncio.to_thread`, matching `workers/tasks.py` / `storage/s3.py` convention |
| Cert file missing/misconfigured, or other `efi_*` settings empty | Eager startup validation (non-empty + `Path.exists()` on cert) raises immediately when `pix_provider == "efi"` — fails at boot, not on the first customer's payment attempt |
| `app_env=production` + `efi_sandbox=true` (near-certain misconfiguration: charges silently land in sandbox) | Loud `loguru` warning at startup on this combination |
| Orphaned real Efí charge if DB commit fails *after* a successful `provider.create_charge` call (pre-existing scaffold ordering in `service.py:72-104` — harmless for the fake provider, but now has a real external side effect) | Accepted as a documented known-risk: small blast radius (a few stray low-value charges, caught on reconciliation); fixing requires touching `PixService` internals, which this phase deliberately keeps untouched. Flagged here as a follow-up: persist the `PixCharge` row in a `creating` state *before* calling the provider |
| Efí sandbox payload / webhook-URL routing drifts from documented (and community-sourced) examples | `verify_webhook` parsing isolated to `efi.py`, tests pin the expected shape; runbook's explicit "verify delivery URL against Efí's dashboard log" step catches routing drift before it becomes a silent production failure |
| Raw SDK/network exceptions surfacing as unhelpful 500s on transient PSP failures | `EfiPixProvider` translates them to `ValidationError` at the boundary — caught by the existing `AppError` handler, contained entirely in `efi.py` |
| `PayerInfo`/`query_params` Protocol changes ripple through fake provider + service + webhook endpoint | All call sites enumerated above; changes are mechanical signature threading, covered by existing test suite plus new assertions |

## Acceptance checklist

- [ ] `PIX_PROVIDER=efi` with valid Efí sandbox credentials creates a real charge; `brcode` + QR PNG returned to the customer portal exactly as the fake flow does.
- [ ] `PayerInfo` correctly built from `Client.cpf_cnpj`/`Client.tipo`/`Client.nome` (digits-only document, explicit `document_type` from `tipo`, not digit-count guessing) and reaches Efí's `devedor` field.
- [ ] Paying the sandbox charge triggers Efí's webhook; `verify_webhook` validates the `hmac` query token, parcela flips to `paid`, audit + webhook-event rows created — mirroring the fake-provider flow's guarantees.
- [ ] Invalid/missing `hmac` token → webhook returns 200, `signature_valid=false`, no state change (same contract as today).
- [ ] Canceling a proposal cancels its pending Efí charges via `PATCH .../cob/:txid`.
- [ ] `pix register-webhook` registers the correct URL; delivery verified against Efí's dashboard log and corrected if it doesn't match `/api/v1/webhooks/pix`.
- [ ] App refuses to boot with `PIX_PROVIDER=efi` and missing/empty `efi_*` settings or a missing cert file; logs a loud warning on `app_env=production` + `efi_sandbox=true`.
- [ ] `StubExternalPixProvider` removed; `pix_admin.py` gate updated to `!= "fake"`; `fake` provider and its demo flow unaffected.
- [ ] Transient Efí/SDK failures surface as a clean `ValidationError` message to the customer, not a raw 500.
- [ ] Setup runbook (incl. cert Docker volume mount) walks a fresh operator from zero to a working sandbox integration, end to end.
