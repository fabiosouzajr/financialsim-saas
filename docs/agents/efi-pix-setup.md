# Efí Pix provider setup

One-time runbook — sandbox account through go-live verification. Re-run `pix register-webhook`
(step 5) whenever the domain or `PIX_WEBHOOK_SECRET` changes — it's idempotent (`PUT`).

## 1. Create an Efí sandbox account

Sign up for Efí's "homologação" (sandbox) environment via their developer portal and register
a Pix key (`chave Pix`) for the recipient account. This becomes `EFI_PIX_KEY`.

## 2. Generate and convert the mTLS certificate

Download the `.p12` certificate from Efí's dashboard and convert it to `.pem` (the `efipay`
SDK expects `.pem`; exact command confirmed from Efí's own docs):

```bash
openssl pkcs12 -in certificado.p12 -out certificado.pem -nodes -password pass:""
```

## 3. Mount the certificate into the container

`EFI_CERTIFICATE_PATH` is an in-container path — the file must be bind-mounted there.
`ops/docker-compose.yml` already follows this pattern for `PDF_OUTPUT_DIR` (the `worker`/`api`
services pair an env var pointing at `/var/lib/finacialsim/pdfs` with a named volume). Mirror
it for the cert on **both** `api` and `worker` (both construct `EfiPixProvider` on startup):

```yaml
environment:
  EFI_CERTIFICATE_PATH: /var/lib/finacialsim/certs/efi.pem
volumes:
  - ./certs/efi.pem:/var/lib/finacialsim/certs/efi.pem:ro
```

## 4. Populate `.env`

```env
EFI_CLIENT_ID=...
EFI_CLIENT_SECRET=...
EFI_CERTIFICATE_PATH=/var/lib/finacialsim/certs/efi.pem
EFI_PIX_KEY=11111111-2222-3333-4444-555555555555
EFI_SANDBOX=true
PIX_PROVIDER=efi
```

The app refuses to boot with `PIX_PROVIDER=efi` if any `EFI_*` setting is empty or the
certificate file doesn't exist — fix `.env` and restart rather than chasing a runtime 500 on
the first customer's "Pagar com Pix" click.

## 5. Register the webhook

```bash
uv run finacialsim-saas pix register-webhook
```

Registers `PUT /v2/webhook/:chave` with
`webhookUrl: "<frontend_base_url>/api/v1/webhooks/pix?hmac=<PIX_WEBHOOK_SECRET>&ignorar="`
and header `x-skip-mtls-checking: true` (required — omitting it causes Efí to default to mTLS
validation, which the Caddy proxy can't satisfy, silently breaking webhook delivery).

## 6. Verify webhook delivery — don't skip this

The `?hmac=...&ignorar=` URL mechanism (prevents Efí from appending `/pix` to the registered
URL) is sourced from a community forum post, not Efí's official docs. If it behaves differently,
the webhook silently 404s — Efí retries up to 9 times then gives up, and "payment confirmation
just doesn't happen" is brutal to debug post-launch.

After registering, Efí sends an automatic test notification. Check **Efí's dashboard delivery
log** for the actual URL/path it called. If it doesn't match `/api/v1/webhooks/pix`, adjust the
registered URL (with/without `/pix`, with/without `?ignorar=`) and re-run step 5.

## 7. Manual smoke test (CobV-shaped)

1. Create a sandbox CobV charge via "Pagar com Pix" on a proposal with a linked client
   (clientless proposals are blocked by design — spec §2b).

2. Confirm the **same `brcode`/QR is payable at three points**: a few days before `vencimento`,
   on `vencimento`, and a few days after — the long-lived single-charge model means all three
   matter, not just "does it work once."

3. Pay via Efí's sandbox simulator. **Explicitly test a value above R$10** to verify/refute
   the "R$0.01–10.00 only" sandbox auto-confirm claim (spec §1 Known Unknown — must be
   confirmed before production confidence). Sandbox charges ≤ R$10.01 auto-confirm without
   a manual simulator step (useful first pass only).

4. Confirm the webhook fires: `parcela` flips to `paid`, `pix_webhook_events`/`audit_logs`
   rows created (check admin UI or query tables directly).

## Hardening deferred to a later phase

Phase 1 ships skip-mTLS + hmac-token validation only — no IP allowlist, no mTLS handshake.
Both depend on reverse-proxy/cert-handling infrastructure not yet configured. Revisit when
Caddy exposes a trustworthy `X-Forwarded-For` or client cert.
