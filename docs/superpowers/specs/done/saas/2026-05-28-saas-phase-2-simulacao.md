# Phase 2 — Core domain port + Simulação

> Bring the central financial flow online: port the desktop simulation pipeline (Price + IOF + extras + CET) behind tenant-scoped REST endpoints, and build the React simulação page.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 1 — Auth + RBAC + Tenant management
> **Successor:** Phase 3 — Cadastros (Clientes + Veículos + FIPE)

## Goal

A logged-in staff user can fill the simulação form, see a live preview, save it, and read it back later — every result matching the desktop centavo-a-centavo on the regression cases.

## In scope

### Data layer

Alembic migration adds:

- `business_rules` — id UUID PK, tenant_id, chave TEXT, valor_json JSONB, descricao, atualizado_em, atualizado_por. Unique `(tenant_id, chave)`.
  - Seeded per-tenant on creation (CLI extended): `entrada_minima_pct`, `prazo_minimo_meses`, `prazo_maximo_meses`, `taxa_minima_mes`, `taxa_maxima_mes`, `dias_max_carencia`, `valor_minimo_financiado`, `iof_fixo_pct`, `iof_diario_pct`, `iof_diario_max_dias`, `incluir_iof_default`, `rateio_ipva_meses_default`, `rateio_emplacamento_meses_default`, `taxa_por_prazo_curva`.
- `simulations` — (`codigo`, `cliente_nome TEXT`, `veiculo_descricao TEXT`, all Decimal fields, `incluir_iof`, `rules_snapshot_json`, `status`, `criado_por`, `idempotency_key TEXT UNIQUE nullable`) plus `tenant_id`. Phase 3 adds `cliente_id UUID FK` and `veiculo_id UUID FK` via migration. Unique `(tenant_id, codigo)`. Status enum: `rascunho | confirmado | arquivado`. `POST /simulations` creates as `confirmado`. `PATCH` only on `rascunho`. Archive works on any status. `POST /clone` always produces `rascunho`.
- `simulation_fees` — `(id, simulation_id, tenant_id, nome, valor, incluir_no_principal)`.
- `simulation_extras` — `(id, simulation_id, tenant_id, tipo, nome, valor_total, modalidade, duracao_meses, valor_por_parcela, ordem)`.
- `amortization_rows` — `(id, simulation_id, tenant_id, numero_parcela, data_vencimento, dias_periodo, saldo_anterior, juros, amortizacao, parcela, saldo_devedor, extras_total, parcela_total, ajuste_arredondamento)`. Index `(simulation_id, numero_parcela)`.
- `simulation_counters` — `(tenant_id UUID PK, year SMALLINT PK, next_val INTEGER NOT NULL DEFAULT 1)`. Row-locked with `SELECT ... FOR UPDATE` to generate `SIM-YYYY-NNNNN` per tenant.
- `extraordinary_amortizations` — table created now (no UI yet); endpoints in v2.
- No Postgres RLS policies in v1 — tenant isolation via app-level `tenant_id` filtering (consistent with Phase 1 decision). Composite FKs `(tenant_id, id)` where dependent.

### Services

- `simulation_service.preview(payload, ctx)` — pure computation, no persistence, no business rule validation. Runs math on whatever the caller provides. Computation order: (1) `base_pv = valor_veiculo - entrada_valor + sum(fees where incluir_no_principal)`; (2) if `incluir_iof`: `compute_financed_amount_with_iof(base_pv, ...)` → `final_pv`; (3) `build_schedule(final_pv, ...)`; (4) `compute_extras_per_parcela(extras, prazo)`; (5) zip rows; (6) `compute_cet(...)`.
- `simulation_service.create(payload, ctx)` — validates against `business_rules`, computes, persists `simulations` + child rows in one transaction, snapshots active rules, generates `codigo` (`SIM-YYYY-NNNNN` per tenant).
- `simulation_service.get(id, ctx)`, `list(filters, ctx)`, `update(id, payload, ctx)` (rascunho only), `archive(id, ctx)`.
- `rules_service.snapshot(ctx)` returns the rules dict used by `create`.

Computation reuses `finacialsim_core`:

- `core.price_table.build_schedule`
- `core.iof.compute_iof` / `compute_financed_amount_with_iof`
- `core.extras.compute_extras_per_parcela`
- `core.cet.compute_cet`
- `core.validators.validate_simulation`

### API endpoints

```text
GET    /api/v1/business-rules        → full rules dict for tenant (used for form defaults + rate suggestion)
POST   /api/v1/simulations/preview   payload → { schedule, summary }
POST   /api/v1/simulations           payload → 201 + simulation
GET    /api/v1/simulations           ?status,?cliente_nome,?date_from,?date_to,?cursor → page (criado_em desc); user sees all tenant sims, writes own only
GET    /api/v1/simulations/{id}      → full simulation incl. rows + extras
PATCH  /api/v1/simulations/{id}      full payload replace (rascunho only); recomputes all child rows
POST   /api/v1/simulations/{id}/archive
POST   /api/v1/simulations/{id}/clone       → 201 + new simulation in rascunho (all fields copied)
```

Ownership scope: `user` can only edit own; `manager`/`admin` can edit any in tenant.

### Frontend

Routes `/simulacao` and `/simulacao/:id`:

- Single-column responsive form (collapses well on tablet/mobile).
- Inputs: valor do veículo, entrada (R$ ↔ % synced), prazo slider (12–72) + input, taxa mensal (badge for suggested rate), datas (liberação, primeiro venc), tarifas (collapsible), IOF toggle, extras (proteção/IPVA/emplacamento/custom with modalidade & duração).
- Live preview via `POST /simulations/preview` debounced 400ms.
- Result cards: Parcela do financiamento, Parcela total 1º ano, Parcela total após rateio, Valor financiado, Total pago, Total juros, % juros, CET a.m./a.a., Total pago pelo cliente.
- Schedule table with extras and parcela_total columns; export CSV.
- Charts (Recharts): composição da parcela (stacked bar), saldo devedor (line), parcela total ao longo do tempo (line with step at end of rateio).
- Cliente / veículo are simple text inputs in this phase; Phase 3 replaces them with pickers.

### Tests

- All `finacialsim_core` tests run unchanged.
- `simulation_service` unit tests: every desktop golden case ported as `pytest` parametrize.
- API integration:
  - `preview` returns same numbers as `create + get`.
  - `create` idempotent under `Idempotency-Key` retry.
  - `create` rejects payloads outside `business_rules` bounds.
- Hypothesis property tests stay green.
- Frontend Vitest: entrada R$ ↔ % sync; debounce fires once per burst.

## Out of scope

- Cliente / veículo CRUD and FIPE picker (Phase 3).
- Indicadores integration / scheduled rate updates (Phase 4).
- Proposta PDF (Phase 5).
- Amortização extraordinária UI.
- Comparativo.

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Decimal precision drift on the wire | `DecimalStr = Annotated[Decimal, PlainSerializer(str), BeforeValidator(Decimal)]` in `schemas/types.py`; React treats all money fields as strings, formats for display only |
| Live preview slams the API | Debounced; pure-compute endpoint, no DB write |
| Rules snapshot bloat | Snapshot only the rules referenced by validation + computation |
| `codigo` collision on concurrent creates | `tenant_id`-scoped Postgres sequence or row-locked counter |

## Acceptance checklist

- [ ] All `finacialsim_core` tests green.
- [ ] Every desktop golden simulação matches centavo-a-centavo through `POST /simulations`.
- [ ] `preview` and `create + get` agree on the full schedule for the same payload.
- [ ] Cross-tenant: tenant A user cannot `GET` tenant B's simulation (404).
- [ ] User role cannot `PATCH` another user's draft; manager/admin can.
- [ ] React simulação page renders, preview updates within ~500ms after edit, save round-trips, reload shows same values.
- [ ] CSV export contains all `amortization_rows` columns including `extras_total` and `parcela_total`.
- [ ] `POST /simulations/{id}/clone` creates a new `rascunho` with all fields copied; original is unchanged.
- [ ] `POST /simulations/preview` p95 < 150ms in CI smoke; `POST /simulations` p95 < 250ms.
