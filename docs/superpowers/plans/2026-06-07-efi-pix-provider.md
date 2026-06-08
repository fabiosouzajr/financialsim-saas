# Efí Pix Provider (Phase 1 — CobV Redesign) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax. This is the **index file** — implementation tasks live in the part files below. Load whichever part covers the next unchecked task.

**Goal:** Replace `StubExternalPixProvider` with a working `EfiPixProvider` targeting Efí's CobV (due-date Pix charge) API, wired through `pix/deps.py`'s provider selector — plus the Protocol/service-layer changes (`PayerInfo`, calendar-anchored `due_date`/`validity_days`, webhook `query_params`, shared idempotent `_ensure_charge` core, clientless-proposal guard) that this requires.

**Architecture:** `EfiPixProvider` wraps the sync `efipay` SDK in `asyncio.to_thread`, targeting `/v2/cobv` (`pix_create_due_charge`/`pix_update_due_charge`) — CobV charges are calendar-anchored to `vencimento` and stay payable for `validadeAposVencimento` days after, so one charge covers a parcela's whole lifecycle (see spec §"Why CobV, not Cob"). `PixService` gains a shared idempotent `_ensure_charge` core (returns `(charge, created)`, mirroring `get_or_create`) so Phase 2's cron can reuse it without duplicating notification logic; `create_charge_for_parcela` becomes a thin customer-facing wrapper around it. `PayerInfo` and webhook `query_params` are generic Protocol changes threaded mechanically through `InMemoryFakePixProvider` / `PixService` / `api/webhooks.py`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, `efipay` SDK v1.0.7 (sync OAuth2+mTLS), `asyncio.to_thread`, `zoneinfo.ZoneInfo` (BRT-anchored expiry), `typer` CLI, `pytest`/`pytest-asyncio`, `MagicMock`/`AsyncMock`.

**Design spec:** `docs/superpowers/specs/2026-06-07-efi-pix-provider-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/pyproject.toml` | Add `efipay>=1.0.7` dependency |
| `backend/finacialsim_saas/settings.py` | New `efi_*` settings fields |
| `backend/finacialsim_saas/services/rules_service.py` | Add `pix_validade_apos_vencimento_dias` (default 60) to `_RULE_DEFAULTS` |
| `backend/alembic/versions/011_seed_pix_validade_apos_vencimento_rule.py` | **New** — seeds the new rule for every tenant |
| `backend/finacialsim_saas/pix/protocol.py` | `PayerInfo` dataclass; `create_charge` signature → `due_date: date, validity_days: int`; `verify_webhook` gains `query_params` |
| `backend/finacialsim_saas/pix/fake.py` | Mechanical threading + BRT-anchored calendar expiry (replaces 30-min TTL) |
| `backend/finacialsim_saas/pix/service.py` | New shared `_ensure_charge` core (returns `(charge, created)`); `create_charge_for_parcela` → thin customer-facing wrapper; `handle_webhook` threads `query_params` |
| `backend/finacialsim_saas/pix/efi.py` | **New** — `EfiPixProvider`: CobV `create_charge` / `cancel_charge` / `verify_webhook` / `register_webhook` |
| `backend/finacialsim_saas/pix/stub.py` | **Deleted** — superseded by `EfiPixProvider` |
| `backend/finacialsim_saas/pix/deps.py` | `efi` branch wiring, cached singleton, startup validation guards |
| `backend/finacialsim_saas/api/webhooks.py` | Thread `query_params` from `request.query_params` |
| `backend/finacialsim_saas/api/pix_admin.py` | Gate rename `== "external"` → `!= "fake"` |
| `backend/finacialsim_saas/main.py` | Fail-fast Pix validation at startup; sandbox-in-production warning |
| `backend/finacialsim_saas/cli/pix_cli.py` | **New** — `pix register-webhook` command |
| `backend/finacialsim_saas/cli/main.py` | Register `pix_app` sub-app (lines 32–36) |
| `docs/agents/efi-pix-setup.md` | **New** — CobV-shaped setup runbook |

---

## Task Parts

| Part | Tasks | Topics |
| --- | --- | --- |
| [Part 1](2026-06-08-efi-pix-provider-plan-part1.md) | 1–4 | Foundation: settings, Protocol (CobV signature), fake provider (BRT expiry), `pix_validade_apos_vencimento_dias` rule + migration |
| [Part 2](2026-06-08-efi-pix-provider-plan-part2.md) | 5–6 | Service: `_ensure_charge` shared core + `create_charge_for_parcela` wrapper; `handle_webhook` query_params |
| [Part 3](2026-06-08-efi-pix-provider-plan-part3.md) | 7–9 | Provider: `EfiPixProvider` CobV `create_charge`, `cancel_charge`, `verify_webhook` |
| [Part 4](2026-06-08-efi-pix-provider-plan-part4.md) | 10–13 | Wiring: `deps.py`, `main.py` lifespan, CLI `register-webhook`, setup runbook + self-review |

---

**Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Use `superpowers:subagent-driven-development`.

**2. Inline Execution** — batch execution with checkpoints. Use `superpowers:executing-plans`.
