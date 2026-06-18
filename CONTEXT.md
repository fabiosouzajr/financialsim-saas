# Domain Glossary

Single-context repo. See `docs/adr/` for architectural decisions.

---

## Core Financing Concepts

**Simulação** (`Simulation`) — a financing scenario: vehicle, buyer, amount, term, rates. The starting point for every proposal. May exist without a linked `Client` (clientless).

**Proposta** (`Proposal`) — a finalized, approved financing offer derived from a `Simulação`. Has a lifecycle (`rascunho → aprovada → cancelada`). One `Proposal` per `Simulation` (unique constraint).

**Parcela** (`ParcelaPayment`) — a single installment payment within an approved `Proposal`. Has a `vencimento` (due date), `valor_parcela`, and a status (`open`, `overdue`, `paid`, `canceled`). The atomic unit of Pix charge creation — one CobV charge is created per `Parcela`, ever.

**Vencimento** — the calendar due date of a `Parcela`. Used as the anchor for both reminder scheduling (cron selects `vencimento == target_date`) and CobV charge creation (`calendario.dataDeVencimento`).

**Extra** — an additional cost appended to each installment within a `Simulação`. Examples: IPVA (annual vehicle tax), Emplacamento (vehicle registration fee), Proteção Veicular. Distributed via a `modalidade`: `mensal_continuo` (every installment), `rateio_ciclico` (annual lump sum spread over N months, recycling each cycle), `rateio_meses` (one-time spread over first N months), `unico_inicial` (first installment only). Stored in `extras` table linked to the simulation.

---

## Pix Concepts

**CobV** — Efí's due-date Pix charge type (`/v2/cobv`). Calendar-anchored to `vencimento`; natively applies `juros`/`multa` for late payments; valid from creation through `vencimento + validadeAposVencimento` days. The only charge type used in this system — no "immediate" (Cob) charges.

**brcode** — the Pix "copia e cola" string (EMV QR payload). Plain text, no expiry of its own. The cron delivers it directly in the due-soon email; the portal renders it alongside the QR PNG.

**pix_valido_ate** — the charge's last valid payment date, displayed to the customer. Derived from `PixCharge.expires_at` (UTC) via a BRT round-trip: `expires_at.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")`. Equals `vencimento + validadeAposVencimento` days in BRT — not the vencimento itself.

**`_ensure_charge`** (`PixService`) — the shared idempotent core for Pix charge creation. Called by both the portal path (`create_charge_for_parcela`) and the cron path (`create_auto_charge_for_parcela`). For open parcelas, returns the existing pending `PixCharge` if one exists. For overdue parcelas with penalty rates configured and past the grace period, regenerates a stale charge (created before today BRT) so the brcode always reflects current interest accrual. Creates a new CobV charge when no valid pending charge exists.

---

## Notification Concepts

**Cobrança automática** — the per-tenant opt-in feature (Phase 2) that proactively generates a Pix charge N days before a `Parcela`'s `vencimento` and embeds the `brcode` in the existing due-soon reminder email. Controlled by two `BusinessRule` keys: `pix_cobranca_automatica_habilitada` (bool, default `False`) and `pix_cobranca_automatica_dias_antes` (int 1–30, default `3`).

**dias_antes** — the lead time (in days) before `vencimento` at which the due-soon reminder is sent and (for enabled tenants) the Pix charge is generated. Per-tenant configurable; defaults to `3` matching today's hardcoded behavior. Threaded into the notification payload for the subject template.

**Outbox drain** — templates render at drain time (`drain_notifications_outbox`), not at enqueue time. Payload is stored as JSON; the Jinja2 template is applied when the outbox row is actually sent. Implication: changing a template affects all pending rows, not just future ones.

---

## Multi-tenancy

**Tenant** — a car dealership (or similar small/mid business) using FinancialSim. Has `id`, `name`, `slug`, `created_at`. No `is_active` field — every row in the `tenants` table is considered active.

**BusinessRule** — a per-tenant configuration key/value stored in `business_rules` table. `RulesService.get_rules(tenant_id)` fills any missing keys from `_RULE_DEFAULTS` at read time. Seed migrations (`010_`, `011_`, …) insert defaults for all existing tenants so rows appear in the admin UI without requiring an explicit set.

---

## Inadimplência Concepts

**Inadimplência** — the state of a `Parcela` being overdue and unpaid (`status = overdue`). Triggers penalty accrual (`multa` + `juros`) per tenant-configured rates once the grace period (`carência`) has passed.

**Multa** — a one-time flat penalty, expressed as a percentage of `valor_parcela` (BACEN ceiling: 2%). Applied once when `dias_atraso > carencia_dias`. Not a fixed BRL amount — "multa fixa" in Brazilian CDC means "one-time, non-accruing" as opposed to daily juros, not a literal fixed value.

**Juros moratórios** (`juros_diario_pct`) — daily interest that accrues from the first day past the grace period. Expressed as a percentage per day (BACEN ceiling: ~0.033%/day = 1%/month). CobV `modalidade: 2` = "Percentual ao dia (dias corridos)".

**Carência** (`carencia_dias`) — grace period in calendar days after `vencimento` before multa and juros start accruing. Implemented at the `_ensure_charge` level (not via a `dataInicio` field — that field does not exist in the BACEN CobV schema). A charge generated within the grace period carries zero rates; the daily regeneration cycle issues a new charge with real rates the first day past grace.

**Encargos** — the combined late-payment charges: `multa + juros_acumulado`. The portal displays a real-time `encargos` estimate (labeled `estimativa: true`) alongside the corrected `valor_corrigido` for overdue parcelas.
