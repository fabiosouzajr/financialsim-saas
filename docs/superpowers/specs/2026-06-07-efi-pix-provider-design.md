# Efí Pix Provider — Phase 1 (PIX básico real)

> Implements the real PSP wiring that Phase 6 deferred: a working `EfiPixProvider` behind the existing `PixProvider` Protocol, replacing `StubExternalPixProvider`. No changes to `PixService`'s business logic, DB schema, frontend, or the fake-provider demo flow.
>
> **Predecessor:** Phase 6 — Portal do cliente + Pix scaffold (`2026-05-28-saas-phase-6-portal-cliente-pix.md`)
> **Roadmap reference:** `docs/prompts/pix-gpt.md` — "FASE 1 — PIX básico"

## Goal

`PIX_PROVIDER=external` produces real PIX charges through Efí (Bank): create an immediate charge, generate a QR code + copia-e-cola, receive payment confirmation via webhook, cancel a charge. End-to-end demo: staff/customer triggers "Pagar com Pix" → real Efí sandbox charge created → customer pays via Efí's sandbox simulator → webhook confirms → `parcela` flips to `paid`, exactly as the fake-provider flow does today.

## In scope

### 1. `EfiPixProvider` (`backend/finacialsim_saas/pix/efi.py`)

Implements `PixProvider` using the official `efipay` Python SDK (sync/`requests`-based), wrapped in `asyncio.to_thread` — the same pattern this codebase already uses for sync libraries inside async code (`workers/tasks.py:292` for WeasyPrint, `storage/s3.py` for boto3).

```python
class EfiPixProvider:
    name = "external"  # matches pix_provider selector value, mirrors fake/stub convention

    def __init__(self, settings: Settings) -> None:
        self._client = EfiPay({
            "client_id": settings.efi_client_id,
            "client_secret": settings.efi_client_secret,
            "sandbox": settings.efi_sandbox,
            "certificate": settings.efi_certificate_path,
        })
        self._pix_key = settings.efi_pix_key
        self._webhook_secret = settings.pix_webhook_secret
```

| Protocol method | Efí REST call (via SDK) | Behavior |
|---|---|---|
| `create_charge` | `PUT /v2/cob/:txid` then `GET /v2/loc/:id/qrcode` | Builds `devedor` from `payer.document`/`payer.name` (CPF if 11 digits, else CNPJ); `valor.original` from `amount`; `chave` from settings; `calendario.expiracao` from `expires_in`. Response gives `pixCopiaECola` (→ `brcode`) and `loc.id`; second call returns base64 QR PNG → decoded into `qr_png_bytes`. Maps Efí's `calendario.criacao + expiracao` to `expires_at`. |
| `cancel_charge` | `PATCH /v2/cob/:txid` `{"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}` | Errors logged and swallowed — `PixService.cancel_charges_for_proposal` already treats provider cancel failures as best-effort (`service.py:319-322`). |
| `verify_webhook` | — (local validation only) | See §3 below: token-in-URL + IP allowlist, NOT body HMAC. Synthesizes `WebhookEvent(status="paid", ...)` from Efí's real payload shape, which carries no explicit status field. |

Exact SDK method names for txid-based create / QR fetch / cancel (`pix_create_immediate_charge` is confirmed; the others are not shown in the doc excerpts) will be pinned down by reading the installed SDK's source/examples during implementation — this is a mechanical lookup, not a design decision.

### 2. `PixProvider` Protocol changes (`pix/protocol.py`)

Two gaps in the current scaffold surfaced by Efí's real API. Both are generic PIX-PSP concepts (not Efí-specific), so fixing them keeps the interface pluggable for any future provider:

**a) Structured payer identity.** Efí requires `devedor: {cpf|cnpj, nome}`; the current `payer: str` (always passed as `""` — a placeholder never wired to real data, `service.py:81`) can't carry that. New dataclass, mirroring the existing `PixChargeData`/`WebhookEvent` convention:

```python
@dataclass
class PayerInfo:
    document: str | None  # CPF or CNPJ, digits only
    name: str | None
```

`create_charge`'s `payer: str` becomes `payer: PayerInfo | None`. `PixService.create_charge_for_parcela` looks up the `Client` (via `Proposal → Simulation → Client`) and passes `PayerInfo(document=client.cpf_cnpj, name=client.nome)`.

**b) Webhook query params.** Efí does not HMAC-sign the body. Their mechanism: a static token embedded in the *registered callback URL's query string* (`?hmac=<token>&ignorar=`); the receiver validates incoming requests carry the same token — a "shared secret in callback URL" pattern other PSPs also use. `verify_webhook` gains a `query_params` parameter:

```python
def verify_webhook(self, headers: dict, query_params: dict, body: bytes) -> WebhookEvent
```

Cascades to: `PixService.handle_webhook(headers, query_params, body)`, `api/webhooks.py` (passes `dict(request.query_params)`), and `InMemoryFakePixProvider.verify_webhook` (accepts the new param, ignores it, keeps its own HMAC-over-body scheme — that's a test convenience, not something a real PSP does).

**No protocol change needed** for the missing `status` field: Efí's real webhook payload (`{"pix": [{"endToEndId", "txid", "chave", "valor", "horario", "infoPagador"}]}`) carries no status — receiving a `pix[]` entry *is* the "received/paid" signal. `EfiPixProvider.verify_webhook` constructs `WebhookEvent(status="paid", txid=entry["txid"], paid_amount=Decimal(entry["valor"]), ...)` directly. `WebhookEvent.status` stays a generic string; the Protocol is unaffected.

### 3. Webhook validation strategy (skip-mTLS)

Efí supports two validation modes:
- **mTLS** (their default recommendation): requires the web server/reverse-proxy to perform mutual-TLS handshakes with Efí's client certificate chain — infrastructure-level work (nginx/traefik config), out of place for a backend-code "Phase 1 básico" change.
- **Skip-mTLS**: register the webhook with `x-skip-mtls-checking: true`; the integrator is responsible for validating the callback's authenticity via (a) a static token they embed in the registered URL's query string, and (b) Efí's fixed sender IP (`34.193.116.226`).

**Decision: skip-mTLS.** `EfiPixProvider.verify_webhook` checks `query_params.get("hmac") == settings.pix_webhook_secret` (constant-time compare) and — where the request's source IP is available — that it matches `34.193.116.226`. This reuses the existing `PIX_WEBHOOK_SECRET` setting (already present from Phase 6) with no schema change. **mTLS is documented as a hardening item for a later phase** (see Out of scope).

### 4. New settings (`settings.py`)

```python
efi_client_id: str = ""
efi_client_secret: str = ""
efi_certificate_path: str = ""   # absolute path to .pem on disk
efi_pix_key: str = ""            # the recipient's registered Pix key (UUID format)
efi_sandbox: bool = True
```

`pix_provider` keeps its existing `fake | external` values; `deps.get_pix_provider` constructs `EfiPixProvider(settings)` when `external` is selected (replacing `StubExternalPixProvider`, which is deleted — its sole purpose, a placeholder for "real PSP wiring," is now fulfilled).

### 5. CLI command: `pix register-webhook`

One-time setup action — registers the callback URL with Efí (`PUT /v2/webhook/:chave`, `webhookUrl: "https://<frontend_base_url>/api/v1/webhooks/pix?hmac=<PIX_WEBHOOK_SECRET>&ignorar="`). Implemented as a `typer` command alongside the existing CLI (`cli/main.py`), reusable whenever the domain or secret changes (env migration, rotation). Idempotent — re-running overwrites the registration with the current URL/secret.

### 6. Setup runbook (new doc: `docs/agents/efi-pix-setup.md` or similar)

Step-by-step guide covering: creating an Efí sandbox ("homologação") account, registering a Pix key, generating + downloading the `.p12` certificate and converting it to `.pem` via OpenSSL, populating `.env` (`EFI_CLIENT_ID`, `EFI_CLIENT_SECRET`, `EFI_CERTIFICATE_PATH`, `EFI_PIX_KEY`, `EFI_SANDBOX=true`, `PIX_PROVIDER=external`), running `pix register-webhook`, and a manual smoke-test checklist (create a sandbox charge, pay it via Efí's sandbox simulator — note: sandbox charges ≤ R$10.01 auto-confirm — confirm webhook flips `parcela` to `paid`).

### Tests

- `EfiPixProvider`: mock the `EfiPay` client at the boundary (inject a stub/`MagicMock` client), assert request payload shape (`devedor`, `valor.original`, `chave`, `calendario.expiracao`) and correct mapping of the SDK response into `PixChargeData` (brcode, decoded QR PNG bytes, `expires_at`).
- `cancel_charge`: asserts `PATCH` payload `{"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}`; provider exception is swallowed (matches existing `cancel_charges_for_proposal` contract).
- `verify_webhook`: matching `hmac` query param → valid; mismatched/missing → raises; real-shaped Efí payload (`{"pix": [{"txid", "valor", "horario", ...}]}`, no `status` field) → `WebhookEvent(status="paid", paid_amount=Decimal(...))`.
- `PixService.create_charge_for_parcela`: asserts `PayerInfo` is correctly built from the `Client` (CPF vs CNPJ based on `cpf_cnpj` length) and threaded through to `provider.create_charge`.
- `pix register-webhook` CLI: asserts the registered URL is built correctly from `frontend_base_url` + `pix_webhook_secret`.
- Real sandbox round-trip (actual cert + creds) is a **manual** verification step in the runbook — not part of automated CI, since it requires a live Efí sandbox account.

## Out of scope

- mTLS webhook validation (documented as a future hardening item — requires reverse-proxy/server-level mutual-TLS configuration).
- Pix Automático, scheduled/recurring Pix.
- Per-tenant Efí accounts (this is a single platform-wide account/cert, matching how the rest of the SaaS centralizes PSP credentials).
- Refund/devolução flows.
- Changes to `PixService` business logic, DB schema, frontend, or the `fake` provider's demo behavior — all of that is Phase 6-complete and stays as-is.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Skip-mTLS leaves webhook authenticity resting on a single shared secret in a URL | Combine with IP allowlist (`34.193.116.226`); document mTLS upgrade path for later hardening |
| Sync SDK blocks the event loop | Wrap every SDK call in `asyncio.to_thread`, matching `workers/tasks.py` / `storage/s3.py` convention |
| Cert file missing/misconfigured at startup | `EfiPixProvider.__init__` is only invoked when `PIX_PROVIDER=external`; setup runbook + CLI registration command surface config errors early, before going live |
| Efí sandbox payload shape drifts from documented examples | `verify_webhook` parsing is isolated to `efi.py`; tests pin the expected shape; runbook smoke test catches drift against the live sandbox |
| `PayerInfo`/`query_params` Protocol changes ripple through fake provider + service + webhook endpoint | All call sites are enumerated above; changes are mechanical signature threading, covered by existing test suite plus new assertions |

## Acceptance checklist

- [ ] `PIX_PROVIDER=external` with valid Efí sandbox credentials creates a real charge; `brcode` + QR PNG returned to the customer portal exactly as the fake flow does.
- [ ] `PayerInfo` correctly built from `Client.cpf_cnpj`/`Client.nome` (CPF vs CNPJ) and reaches Efí's `devedor` field.
- [ ] Paying the sandbox charge triggers Efí's webhook; `verify_webhook` validates the `hmac` query token, parcela flips to `paid`, audit + webhook-event rows created — mirroring the fake-provider flow's guarantees.
- [ ] Invalid/missing `hmac` token → webhook returns 200, `signature_valid=false`, no state change (same contract as today).
- [ ] Canceling a proposal cancels its pending Efí charges via `PATCH .../cob/:txid`.
- [ ] `pix register-webhook` registers the correct URL (verifiable via Efí's webhook query endpoint or dashboard).
- [ ] `StubExternalPixProvider` removed; `fake` provider and its demo flow unaffected.
- [ ] Setup runbook walks a fresh operator from zero to a working sandbox integration, end to end.
