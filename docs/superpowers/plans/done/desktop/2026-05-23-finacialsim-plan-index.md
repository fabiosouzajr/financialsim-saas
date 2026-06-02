# FinacialSim — Implementation Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement these plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build FinacialSim from zero — a NiceGUI desktop app for Brazilian vehicle financing simulation with bank-grade calculations (Tabela Price + dias corridos + IOF opcional + extras + CET via TIR).

**Architecture:** Modular monolith in layers (`core` / `data` / `integrations` / `services` / `ui`). The `core/` layer is pure (no DB/UI), tested exhaustively. Each upper layer depends only on layers below it.

**Tech Stack:** Python 3.12+, NiceGUI, SQLAlchemy 2.x + Alembic, SQLite, `decimal.Decimal`, scipy, Plotly, WeasyPrint, PyInstaller.

---

## Reference

- Spec: [`docs/superpowers/specs/2026-05-23-finacialsim-design.md`](../specs/2026-05-23-finacialsim-design.md)
- Total phases: **6**
- Total tasks (approx): **~70**
- Each phase is its own file. Execute in order — most depend on lower phases.

---

## Phase order & dependencies

```text
Phase 1 (Core)  ──┬──► Phase 2 (Data)  ──┐
                  │                       ├──► Phase 4 (Services) ──► Phase 5 (UI) ──► Phase 6 (PDF/Pkg)
                  └──► Phase 3 (Integ.) ──┘
```

**Phases 2 and 3 can run in parallel** after Phase 1. Phase 4 needs all three. Phase 5 needs Phase 4. Phase 6 needs all previous.

---

## Phase summary

| # | File | Focus | Tasks |
| --- | --- | --- | --- |
| 1 | [`2026-05-23-phase-1-core.md`](2026-05-23-phase-1-core.md) | Pure financial domain (Decimal, Tabela Price, IOF, CET, extras, validators) | 16 |
| 2 | [`2026-05-23-phase-2-data.md`](2026-05-23-phase-2-data.md) | SQLAlchemy models, Alembic migrations, repositories, backup | 10 |
| 3 | [`2026-05-23-phase-3-integrations.md`](2026-05-23-phase-3-integrations.md) | ProviderChain, FIPE (Parallelum + BrasilAPI), BACEN SGS | 9 |
| 4 | [`2026-05-23-phase-4-services.md`](2026-05-23-phase-4-services.md) | Auth, client, simulation, comparison, proposal, indicators, audit | 11 |
| 5 | [`2026-05-23-phase-5-ui.md`](2026-05-23-phase-5-ui.md) | NiceGUI theme + components + 10 pages + router | 14 |
| 6 | [`2026-05-23-phase-6-pdf-packaging.md`](2026-05-23-phase-6-pdf-packaging.md) | WeasyPrint PDF, PyInstaller, install scripts, CI release | 8 |

---

## Conventions

All phases follow these rules:

- **TDD strict in Phase 1 + Phase 2 + Phase 4** (the bug-sensitive layers). Phases 3/5/6 use TDD where useful, with manual verification for UI/external APIs.
- **One commit per task** (sometimes per step in Phase 1).
- **`decimal.Decimal` everywhere** financial. Never `float`.
- **Type-checked** with `mypy --strict` on `core/`, `mypy` (non-strict) on rest.
- **Linted** with `ruff` everywhere.
- Use **`pytest -xvs`** when developing, `pytest` (no flags) in CI.
- **Idiomatic Python 3.12+** (`match`, `Self`, PEP 695 type aliases when helpful).
- Tests live next to module in `tests/unit/<layer>/test_<module>.py`.
- Integration tests in `tests/integration/`.

## Branch & commit conventions

- `master` always green (CI must pass).
- Phase branches: `phase-1-core`, `phase-2-data`, ...
- Conventional commits: `feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`.
- Task-level commits encouraged. Squash before merge if needed.

---

## Done = MVP

When all 6 phases complete and the acceptance criteria in spec §17 pass on Windows 10, Ubuntu 22.04, and macOS 12+, the MVP is ready.
