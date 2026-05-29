# Phase 4 — Indicadores + Business Rules UI + Scheduler + Audit log

> Bring economic indicators online (BACEN chain, daily scheduled refresh), expose business rules CRUD to admins, and stand up the audit log surface used by every later phase.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 3 — Cadastros (runs in parallel with Phase 5; does not block it)
> **Successor:** Phase 6 — Portal do cliente + Pix scaffold (after Phase 5 is stable)

## Goal

Indicators are fresh daily without manual action, admins can edit business rules with full audit trail, and every CUD operation on tenant-scoped tables since Phase 1 produces an audit_log entry that the UI can browse.

## In scope

### Data layer

- `indicators_history` (global, no tenant_id) — `(id, codigo, data_referencia, valor, unidade, fonte, payload_json, coletado_em)`. Unique `(codigo, data_referencia)`.
- `audit_log` — table pre-created in Phase 1; no migration needed here. This phase wires `audit_service.log()` calls into every CUD service path and adds the browsable UI.

### Services

- `indicators_service.latest(codigo)` — latest global value; carries `stale=True` when older than the codigo's max-age.
- `indicators_service.series(codigo, range)` — historical points.
- `rules_service.list/get/update(chave, valor, ctx)` — admin-only; updates `business_rules` + audit entry; broadcasts `rules.invalidated` over Redis pub/sub.
- `audit_service.log(acao, entidade, entidade_id, diff, ctx)` — explicit calls from every CUD service path.
- `audit_service.list(filters, ctx)` — paginated; role-scoped (`user` own; `manager`/`admin` whole tenant).

### Scheduled jobs (ARQ)

| Job | Frequency | Action |
|---|---|---|
| `update_bacen_indicators` | Daily 09:00 BRT | Refresh SELIC/CDI/IPCA/TX_BACEN_VEIC; upsert into `indicators_history`; one audit_log per tenant tagged `acao='scheduled_job'`. |
| `prune_fipe_cache` | Daily 03:00 BRT | Delete rows beyond TTL. |
| `verify_provider_health` | Every 6 h | Ping each provider; record latency/success into a `provider_health` rolling table (last 50 calls). |

Failures: counter increment, yellow badge on indicators page; never block requests; warning logs.

### API endpoints

```
GET    /api/v1/indicators                        (any staff) → latest of all codigos
GET    /api/v1/indicators/{codigo}/series        ?range=12m

GET    /api/v1/business-rules                    (manager/admin read; admin write)
PUT    /api/v1/business-rules/{chave}            (admin)    { valor }

GET    /api/v1/audit-log                         ?usuario_id,?entidade,?acao,?date_range,?cursor
                                                 user: own only; manager/admin: tenant
```

### Frontend

- `/indicadores` — cards for SELIC/CDI/IPCA/TX_BACEN_VEIC with current value, source badge, fresh/stale tag, 12-month mini chart. Admin: "↻ Atualizar agora" button (enqueues the job).
- `/configuracoes/regras` (admin) — table of every `chave` with inline edit; complex values (`taxa_por_prazo_curva`) get a structured editor; save shows diff confirmation.
- `/logs` (manager/admin) — paginated table with filters; expandable rows show formatted `diff_json`; CSV export.
- Toast on any `business_rules` change so open simulação forms recompute.

### Tests

- BACEN chain tests with httpx mocks: primary OK / primary fail-fallback OK / both fail-cache hit.
- `update_bacen_indicators` ARQ task via in-process runner; asserts idempotent upsert.
- `rules_service.update` emits Redis event; in-process subscriber receives.
- `audit_service` snapshot: a simulação create+update yields two entries with correct `diff_json`.
- Cross-tenant: tenant B admin cannot see tenant A's audit log; `user` cannot see another user's entries.

## Out of scope

- Custom indicator codigos beyond the four canonical.
- Audit log retention / archival.
- Email notifications on rule changes (Phase 7).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| BACEN rate limits / holiday gaps | Cache; idempotent upsert; last-value-carries-forward per BACEN spec |
| Scheduled job double-runs | ARQ task acquires Redis lock keyed `tenant_id + job_name + date`; second invocation no-ops |
| Override misuse | Admin-only; mandatory `motivo`; `manual` badge with the user who set it |
| audit_log growth | `(tenant_id, timestamp DESC)` index; cursor pagination |

## Acceptance checklist

- [ ] Trigger `update_bacen_indicators` manually; all four codigos populate.
- [ ] `/indicadores` renders cards with fresh values and 12-month chart.
- [ ] Admin edits `entrada_minima_pct`; next preview reflects new bound; audit entry exists.
- [ ] `/logs` filters by `acao`, `entidade`, date range; CSV export contains diff.
- [ ] `user` role sees only own logs.
- [ ] ARQ lock prevents double-run within a second.
- [ ] Cross-tenant audit isolation verified.
