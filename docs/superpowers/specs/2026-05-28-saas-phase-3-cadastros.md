# Phase 3 — Cadastros (Clientes + Veículos + FIPE)

> Tenant-scoped CRUD for clients and vehicles, FIPE provider chain ported with Postgres-backed cache, and React UIs (list + modal + FIPE cascade picker) that replace the text inputs left in Phase 2.
>
> **Roadmap:** `2026-05-28-saas-roadmap.md`
> **Predecessor:** Phase 2 — Core domain port + Simulação
> **Successor (critical path):** Phase 5 — Propostas + PDF/Carnê
> **Successor (parallel):** Phase 4 — Indicadores + Business Rules UI (does not block Phase 5)

## Goal

A staff user can register PF/PJ clients with mod-11 validation and CEP autocomplete, register vehicles via FIPE cascade picker or manual entry, and pick them in the simulação form.

## In scope

### Data layer

- `clients` — `(id, tenant_id, nome, cpf_cnpj, tipo PF|PJ, rg, data_nasc, profissao, renda, telefone, email, endereco_json, observacoes, criado_por, criado_em, atualizado_em)`. Unique `(tenant_id, cpf_cnpj)`. App-level `tenant_id` filtering (no RLS in v1).
- `vehicles` — `(id, tenant_id, fonte, tipo, marca, modelo, ano_modelo, combustivel, codigo_fipe, valor_fipe, valor_referencia, mes_referencia_fipe, cor, placa, odometro_km, status, snapshot_json, criado_por, criado_em, atualizado_em)`. Unique `(tenant_id, placa)` where not null. App-level `tenant_id` filtering (no RLS in v1).
- `fipe_cache` — global table (no `tenant_id`): `(id, tipo, acao, marca_id, modelo_id, ano_id, payload_json, coletado_em, ttl_horas)`. Unique `(tipo, acao, marca_id, modelo_id, ano_id)`. No RLS — FIPE data is entirely public; all tenants share cache hits.

### Services

- `client_service.create/get/list/update/deactivate` with mod-11 via `finacialsim_core.utils.document_validation`.
- `vehicle_service.create_from_fipe`, `create_manual`, `update`, `set_status`, `list_active`, `list_all`, `refresh_fipe`.
- `fipe_service`: wraps `finacialsim_core.integrations.fipe.factory.build_fipe_chain`; cache layer is `PostgresFipeCache`.
- `cep_service.lookup(cep)` calls BrasilAPI; fail-open returns empty payload.

### API endpoints

```text
GET    /api/v1/clients                ?q,?cursor → page
POST   /api/v1/clients                → 201
GET    /api/v1/clients/{id}
PATCH  /api/v1/clients/{id}
POST   /api/v1/clients/{id}/deactivate
GET    /api/v1/cep/{cep}              proxy + cache

GET    /api/v1/vehicles               ?status,?placa,?cursor → page
POST   /api/v1/vehicles               (FIPE-sourced or manual)
GET    /api/v1/vehicles/{id}
PATCH  /api/v1/vehicles/{id}
POST   /api/v1/vehicles/{id}/refresh-fipe
POST   /api/v1/vehicles/{id}/status   { status }

GET    /api/v1/fipe/types
GET    /api/v1/fipe/brands?tipo=
GET    /api/v1/fipe/models?tipo=&brand_id=
GET    /api/v1/fipe/years?tipo=&brand_id=&model_id=
GET    /api/v1/fipe/price?tipo=&brand_id=&model_id=&year_id=
```

### Frontend

- `/clientes` list + create/edit modal (PF/PJ toggle, mod-11, CEP autocomplete).
- `/veiculos` list + create modal with FIPE cascade picker + manual fallback toggle.
- Status chips with role-gated action buttons.
- Simulação form replaces text inputs with Client / Vehicle pickers.
- Empty/error states for FIPE failure: yellow badge + retry + "preencher manualmente".

### Tests

- Port `tests/integration/test_vehicle_simulation_flow.py`.
- FIPE chain tests with httpx mocks: primary OK / primary-fail-fallback-OK / both-fail-cache-hit / both-fail-no-cache-manual.
- CPF/CNPJ mod-11 tests carry over.
- Frontend Vitest: PF/PJ toggle swaps fields; inline mod-11; FIPE cascade clears children on parent change.

## Out of scope

- Vehicle inventory dashboard / reports.
- Bulk import.
- Photo uploads.

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| FIPE rate limits | Postgres cache (30 d lists, 24 h price); per-tenant prevents one tenant starving others |
| BrasilAPI CEP downtime | Fail-open; user fills manually |
| Placa format drift | Validator covers antiga + Mercosul |

## Acceptance checklist

- [ ] Create PF and PJ clients; cross-tenant 404.
- [ ] Invalid mod-11 rejected with field-level error.
- [ ] FIPE cascade picker creates a vehicle with `fonte='fipe_parallelum'` (or fallback) and snapshot_json.
- [ ] Manual entry works when both providers are stubbed to fail.
- [ ] Status transitions enforced; illegal rejected.
- [ ] Simulação form now picks existing client + vehicle; saved sim has the FK link.
- [ ] FIPE cache hits logged in structured JSON logs (cache hits/misses tagged in loguru output).
- [ ] CEP autocomplete fills endereço when BrasilAPI responds; empty when stubbed error.
- [ ] Tenant A's vehicles/clients invisible to tenant B.
