# Domain Glossary

Single-context repo. See `docs/adr/` for architectural decisions.

---

## Core Financing Concepts

**Simulação** (`Simulation`) — a financing scenario: vehicle, buyer, amount, term, rates. The starting point for every proposal. May exist without a linked `Client` (clientless).

**Proposta** (`Proposal`) — a finalized, approved financing offer derived from a `Simulação`. Has a lifecycle (`rascunho → aprovada → cancelada`). One `Proposal` per `Simulation` (unique constraint).

**Parcela** (`ParcelaPayment`) — a single installment payment within an approved `Proposal`. Has a `vencimento` (due date), `valor_parcela`, and a status (`open`, `overdue`, `paid`, `canceled`). The atomic unit of Pix charge creation — one CobV charge is created per `Parcela`, ever.

**Vencimento** — the calendar due date of a `Parcela`. Used as the anchor for both reminder scheduling (cron selects `vencimento == target_date`) and CobV charge creation (`calendario.dataDeVencimento`).

---

## Pix Concepts

**CobV** — Efí's due-date Pix charge type (`/v2/cobv`). Calendar-anchored to `vencimento`; natively applies `juros`/`multa` for late payments; valid from creation through `vencimento + validadeAposVencimento` days. The only charge type used in this system — no "immediate" (Cob) charges.

**brcode** — the Pix "copia e cola" string (EMV QR payload). Plain text, no expiry of its own. The cron delivers it directly in the due-soon email; the portal renders it alongside the QR PNG.

**pix_valido_ate** — the charge's last valid payment date, displayed to the customer. Derived from `PixCharge.expires_at` (UTC) via a BRT round-trip: `expires_at.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")`. Equals `vencimento + validadeAposVencimento` days in BRT — not the vencimento itself.

**`_ensure_charge`** (`PixService`) — the shared idempotent core for Pix charge creation. Called by both the portal path (`create_charge_for_parcela`) and the cron path (`create_auto_charge_for_parcela`). Returns the existing pending `PixCharge` if one exists, or creates a new CobV charge via the provider. Either trigger always resolves to the same charge — no duplicate provider calls, no duplicate rows.

---

## Notification Concepts

**Cobrança automática** — the per-tenant opt-in feature (Phase 2) that proactively generates a Pix charge N days before a `Parcela`'s `vencimento` and embeds the `brcode` in the existing due-soon reminder email. Controlled by two `BusinessRule` keys: `pix_cobranca_automatica_habilitada` (bool, default `False`) and `pix_cobranca_automatica_dias_antes` (int 1–30, default `3`).

**dias_antes** — the lead time (in days) before `vencimento` at which the due-soon reminder is sent and (for enabled tenants) the Pix charge is generated. Per-tenant configurable; defaults to `3` matching today's hardcoded behavior. Threaded into the notification payload for the subject template.

**Outbox drain** — templates render at drain time (`drain_notifications_outbox`), not at enqueue time. Payload is stored as JSON; the Jinja2 template is applied when the outbox row is actually sent. Implication: changing a template affects all pending rows, not just future ones.

---

## Multi-tenancy

**Tenant** — a car dealership (or similar small/mid business) using FinancialSim. Has `id`, `name`, `slug`, `created_at`. No `is_active` field — every row in the `tenants` table is considered active.

**BusinessRule** — a per-tenant configuration key/value stored in `business_rules` table. `RulesService.get_rules(tenant_id)` fills any missing keys from `_RULE_DEFAULTS` at read time. Seed migrations (`010_`, `011_`, …) insert defaults for all existing tenants so rows appear in the admin UI without requiring an explicit set.
