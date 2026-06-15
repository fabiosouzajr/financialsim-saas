# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-06-15T17:57:32.506Z
> Files: 388 tracked | Anatomy hits: 0 | Misses: 0

## ../../../../mnt/c/Users/Fabiojr/AppData/Roaming/Antigravity IDE/User/

- `settings.json` (~194 tok)

## ../../.claude/

- `settings.json` (~496 tok)

## ./

- `.dockerignore` (~23 tok)
- `.gitignore` — Git ignore rules (~1099 tok)
- `CLAUDE.md` — CLAUDE.md (~1980 tok)
- `CONTEXT.md` — Domain Glossary (~1324 tok)
- `dev.sh` — dev.sh — FinacialSim SaaS local dev runner (~2996 tok)
- `pyproject.toml` (~34 tok)
- `README.md` — Project documentation (~1467 tok)
- `setup-tenant.sh` — setup-tenant.sh — FinacialSim SaaS first-tenant setup wizard (~1710 tok)

## .claude/

- `settings.json` (~667 tok)
- `settings.local.json` (~34 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .github/workflows/

- `ci.yml` — CI: CI (~630 tok)

## .superpowers/brainstorm/179066-1780498739/content/

- `layout-v2.html` (~2077 tok)
- `layout.html` (~2213 tok)
- `rules-edit.html` (~2222 tok)
- `waiting.html` (~39 tok)

## backend/

- `pyproject.toml` (~327 tok)
- `smoke_weasyprint.py` — Run once locally to verify WeasyPrint renders on Linux. Delete after passing. (~924 tok)

## backend/alembic/

- `env.py` — get_url, run_migrations_offline, do_run_migrations, run_async_migrations (~436 tok)

## backend/alembic/versions/

- `001_create_tenants.py` — create tenants table (~240 tok)
- `002_auth_tables.py` — auth tables — users, password_reset_tokens, refresh_tokens, audit_log, notifications_outbox (~1538 tok)
- `003_simulation_tables.py` — simulation tables — business_rules, simulation_counters, simulations, fees, extras, rows, extraordin (~2290 tok)
- `004_cadastros.py` — cadastros — clients, vehicles, fipe_cache + FK columns on simulations (~1675 tok)
- `004_cadastros.py` — cadastros — clients, vehicles, fipe_cache + FK columns on simulations (~1693 tok)
- `005_indicators_provider_health.py` — indicators_history and provider_health tables (~606 tok)
- `006_proposals.py` — proposals and parcela_payments tables (~1198 tok)
- `007_phase6_pix.py` — phase6 — pix_charges, pix_webhook_events, parcela_payments updates (~1226 tok)
- `008_phase7_notifications.py` — phase7 — finalize notifications_outbox schema; add email_log stub (~998 tok)
- `009_system_settings.py` — system_settings global config table (~227 tok)
- `010_seed_ipva_emplacamento_rules.py` — seed IPVA and emplacamento business rules for all tenants (~434 tok)
- `011_seed_pix_validade_apos_vencimento_rule.py` — seed pix_validade_apos_vencimento_dias business rule (~319 tok)
- `012_seed_inadimplencia_rules.py` — seed inadimplencia business rules for all tenants (~379 tok)

## backend/finacialsim_saas/

- `__init__.py` — FinacialSim SaaS backend. (~10 tok)
- `errors.py` — Declares AppError (~368 tok)
- `main.py` — API router (~1767 tok)
- `settings.py` — Resolve .env relative to this file so alembic (run from backend/) finds it (~556 tok)

## backend/finacialsim_saas/api/

- `admin_health.py` — API: 1 endpoints (~511 tok)
- `admin_settings.py` — API: 2 endpoints (~457 tok)
- `audit_log.py` — API: 1 endpoints (~659 tok)
- `auth.py` — API: 5 endpoints (~820 tok)
- `business_rules.py` — API: 2 endpoints (~838 tok)
- `cep.py` — API: 1 endpoints (~70 tok)
- `clients.py` — API: 6 endpoints (~964 tok)
- `fipe.py` — API: 5 endpoints (~727 tok)
- `health.py` — API: 2 endpoints (~387 tok)
- `indicators.py` — API: 3 endpoints (~442 tok)
- `pix_admin.py` — Staff Pix admin endpoints — manager|admin only. (~1172 tok)
- `portal.py` — Portal API endpoints — customer-facing (role=customer JWT required). (~1464 tok)
- `proposals.py` — Proposal API endpoints. (~1294 tok)
- `simulations.py` — API: 7 endpoints (~1042 tok)
- `storage.py` — Storage serve endpoint — validates HMAC token and streams the file. (~368 tok)
- `users.py` — API: 4 endpoints (~1214 tok)
- `vehicles.py` — API: 6 endpoints (~855 tok)
- `vehicles.py` — API: 6 endpoints (~871 tok)
- `webhooks.py` — PSP webhook endpoints — no JWT auth; HMAC-SHA256 verified per provider. (~312 tok)

## backend/finacialsim_saas/auth/

- `__init__.py` (~0 tok)
- `deps.py` — from: get_db_session, get_current_ctx, require_role (~820 tok)
- `schemas.py` — Declares LoginRequest (~267 tok)
- `service.py` — AuthService: register_user, authenticate, issue_tokens, rotate_refresh + 6 more (~3254 tok)

## backend/finacialsim_saas/cli/

- `__init__.py` (~0 tok)
- `db.py` — db_migrate, db_reset (~540 tok)
- `main.py` — tenant_create, user_create, user_reset_password (~1342 tok)
- `notifications_cli.py` — notifications_drain, notifications_retry (~873 tok)
- `pix_cli.py` — pix_register_webhook (~252 tok)

## backend/finacialsim_saas/data/

- `database.py` — Base: build_engine, build_session_factory, check_db (~252 tok)
- `models.py` — Declares as (~8775 tok)

## backend/finacialsim_saas/integrations/

- `__init__.py` (~0 tok)
- `__init__.py` (~0 tok)

## backend/finacialsim_saas/integrations/bacen/

- `__init__.py` (~0 tok)
- `__init__.py` (~0 tok)
- `brasilapi.py` — BrasilApiBacenProvider: fetch (~568 tok)
- `brasilapi.py` — BrasilApiBacenProvider: fetch (~555 tok)
- `schema.py` — Declares from (~114 tok)
- `schema.py` — Declares from (~111 tok)
- `sgs.py` — BcbSgsProvider: fetch (~748 tok)
- `sgs.py` — BcbSgsProvider: fetch (~748 tok)

## backend/finacialsim_saas/middleware/

- `logging.py` — Context vars set by auth/deps.py after JWT decoding — read by the patcher (~685 tok)

## backend/finacialsim_saas/notifications/

- `__init__.py` (~0 tok)
- `channel.py` — EmailChannel: send (~329 tok)
- `service.py` — NotificationService: render_template, enqueue (~769 tok)

## backend/finacialsim_saas/notifications/templates/auth/password_reset/

- `body.html` — Redefinição de senha (~180 tok)
- `body.txt` (~69 tok)
- `subject.txt` (~9 tok)

## backend/finacialsim_saas/notifications/templates/auth/user_invite/

- `body.html` — Bem-vindo ao FinacialSim (~179 tok)
- `body.txt` (~62 tok)
- `subject.txt` (~12 tok)

## backend/finacialsim_saas/notifications/templates/portal/customer_invite/

- `body.html` — Portal de financiamento (~181 tok)
- `body.txt` (~60 tok)
- `subject.txt` (~14 tok)

## backend/finacialsim_saas/notifications/templates/portal/parcela_due_soon/

- `body.html` — Parcela vence em breve (~142 tok)
- `body.txt` (~59 tok)
- `subject.txt` (~13 tok)

## backend/finacialsim_saas/notifications/templates/portal/parcela_overdue/

- `body.html` — Parcela vencida (~143 tok)
- `body.txt` (~69 tok)
- `subject.txt` (~17 tok)

## backend/finacialsim_saas/notifications/templates/portal/parcela_paid/

- `body.html` — Pagamento confirmado (~141 tok)
- `body.txt` (~37 tok)
- `subject.txt` (~13 tok)

## backend/finacialsim_saas/notifications/templates/portal/pix_link/

- `body.html` — Pix disponível (~181 tok)
- `body.txt` (~61 tok)
- `subject.txt` (~17 tok)

## backend/finacialsim_saas/pix/

- `__init__.py` — Exports PixProvider, PixChargeData, WebhookEvent (~41 tok)
- `deps.py` — get_pix_provider with cached EfiPixProvider singleton and _validate_efi_settings (~490 tok)
- `efi.py` — EfiPixProvider: create_charge (CobV), cancel_charge, register_webhook, verify_webhook (hmac token) (~1402 tok)
- `fake.py` — InMemoryFakePixProvider: create_charge, cancel_charge, verify_webhook (~808 tok)
- `protocol.py` — PixProvider Protocol + PixChargeData, PayerInfo, WebhookEvent dataclasses (~440 tok)
- `service.py` — PixService: _ensure_charge (idempotent CobV), create_charge_for_parcela, handle_webhook (~4602 tok)

## backend/finacialsim_saas/reports/

- `carne.css` — CSS styles for payment booklet PDF (~200 tok)
- `carne.html` — Jinja2 HTML template for payment booklet (carnê) PDF (~500 tok)
- `proposta.css` — CSS styles for proposal PDF report (~200 tok)
- `proposta.html` — Jinja2 HTML template for proposal PDF report (~500 tok)

## backend/finacialsim_saas/schemas/

- `__init__.py` (~0 tok)
- `admin_settings.py` — Declares SettingItem (~54 tok)
- `audit_log.py` — Declares AuditLogItem (~138 tok)
- `business_rules.py` — Declares RateCurvePointOut (~334 tok)
- `clients.py` — Declares ClientIn (~381 tok)
- `fipe.py` — Declares FipeBrandItem (~154 tok)
- `indicators.py` — Declares IndicatorOut (~408 tok)
- `proposals.py` — Proposal schemas: PropostaSnapshot (sealed) + API request/response models. (~1772 tok)
- `simulations.py` — Declares FeeIn (~1052 tok)
- `types.py` (~84 tok)
- `vehicles.py` — Declares VehicleIn (~482 tok)

## backend/finacialsim_saas/services/

- `__init__.py` (~0 tok)
- `audit_service.py` — AuditService: log, list (~947 tok)
- `cep_service.py` — lookup_cep (~196 tok)
- `client_service.py` — ClientService: create, get, list, update + 1 more (~2079 tok)
- `fipe_cache.py` — PostgresFipeCache: name, fetch (~1427 tok)
- `fipe_service.py` — FipeService: build_fipe_chain, get_brands, get_models, get_years + 1 more (~745 tok)
- `indicators_service.py` — IndicatorsService: upsert, latest, latest_all, series (~1300 tok)
- `parcela_service.py` — ParcelaService: list_for_customer, get_schedule, get_parcela, mark_overdue (~2917 tok)
- `proposal_service.py` — ProposalService — manages the full proposal lifecycle. (~3092 tok)
- `rules_service.py` — Single source of truth for all business rule defaults: key → (value, description) (~1669 tok)
- `settings_service.py` — SettingsService: get_all, update (~684 tok)
- `simulation_service.py` — from: preview, create (~8192 tok)
- `vehicle_service.py` — VehicleService: create, get, list, update + 2 more (~2393 tok)

## backend/finacialsim_saas/storage/

- `__init__.py` — StorageBackend Protocol. (~120 tok)
- `deps.py` — Build storage backend from settings. (~186 tok)
- `local.py` — LocalVolumeBackend — stores files on disk; signs URLs with HMAC-SHA256. (~474 tok)
- `s3.py` — S3Backend — boto3 against any S3-compatible endpoint (AWS S3, MinIO, R2). (~493 tok)

## backend/finacialsim_saas/utils/

- `__init__.py` (~0 tok)
- `br_format.py` — Brazilian display formatters: R$, %, dd/mm/yyyy, CPF/CNPJ. (~306 tok)

## backend/finacialsim_saas/workers/

- `notifications.py` — drain_notifications_outbox, schedule_parcela_due_reminders (~2073 tok)
- `tasks.py` — ping, update_bacen_indicators, prune_fipe_cache, verify_provider_health (~3788 tok)
- `worker.py` — WorkerSettings: get_redis_settings, startup, shutdown (~754 tok)

## backend/tests/

- `conftest.py` — ── Postgres ────────────────────────────────────────────────────────────────── (~1146 tok)
- `test_admin_health.py` — test_admin_health_returns_expected_shape, test_admin_health_non_admin_returns_403 (~653 tok)
- `test_admin_settings.py` — clean_settings, test_get_settings_returns_env_defaults, test_put_get_round_trip, test_put_non_admin_ (~1055 tok)
- `test_arq_jobs.py` — test_update_bacen_indicators_populates_db, test_verify_provider_health_prunes_to_50 (~1068 tok)
- `test_audit_backfill.py` — Integration tests: every CUD operation produces a correct audit_log entry. (~1904 tok)
- `test_audit_email_enrichment.py` — test_audit_log_includes_usuario_email (~476 tok)
- `test_audit_log_endpoints.py` — test_audit_log_returns_entries, test_audit_log_filter_by_acao, test_audit_log_user_role_sees_only_ow (~1204 tok)
- `test_audit_service.py` — test_log_and_list, test_list_user_sees_only_own, test_cursor_pagination, test_cross_tenant_isolation (~1019 tok)
- `test_auth_endpoints.py` — seed, test_login_returns_tokens, test_login_wrong_password_returns_401, test_refresh_returns_new_tok (~850 tok)
- `test_auth_invite.py` — tenant, admin_user, client_record, test_invite_customer_creates_user_and_token (~1305 tok)
- `test_auth_service.py` — tenant, test_register_and_authenticate, test_authenticate_wrong_password_raises, test_issue_tokens_r (~1184 tok)
- `test_bacen_providers.py` — test_sgs_primary_ok, test_sgs_http_error_returns_err, test_chain_primary_fail_brasilapi_fallback, te (~1058 tok)
- `test_br_format.py` — test_format_brl_basic, test_format_brl_negative, test_format_brl_large, test_format_pct_default (~289 tok)
- `test_business_rules_update.py` — test_put_business_rule_updates_value, test_put_business_rule_non_admin_forbidden, test_put_business_ (~832 tok)
- `test_cep_service.py` — test_cep_lookup_returns_brasilapi_response, test_cep_lookup_fails_open_on_error, test_cep_invalid_le (~317 tok)
- `test_cli.py` — _FakeProvider: runner, test_tenant_create_and_user_create, test_db_migrate_runs_without_error, test_ (~1038 tok)
- `test_client_endpoints.py` — test_create_and_get_client, test_create_client_invalid_cpf_returns_422, test_deactivate_client, test (~802 tok)
- `test_client_service.py` — ctx_and_session, test_create_pf_client_valid_cpf, test_create_pf_client_invalid_cpf_raises, test_cre (~976 tok)
- `test_database.py` — test_db_ping, test_session_can_execute_query (~124 tok)
- `test_deps_client_id.py` — _Req: test_parse_bearer_includes_client_id, test_parse_bearer_no_client_id_for_staff (~491 tok)
- `test_deps.py` — test_parse_bearer_valid_token, test_parse_bearer_no_header_returns_none, test_require_role_wrong_rol (~607 tok)
- `test_drain_outbox.py` — Tests for drain_notifications_outbox ARQ job (SMTP mocked). (~1790 tok)
- `test_efi_pix_provider.py` — test_create_charge_sends_cobv_request_shape_and_maps_response, test_create_charge_with_penalty_rates (~2417 tok)
- `test_errors.py` — test_not_found_code_and_status, test_external_provider_degraded_flag, test_all_six_errors_are_app_er (~255 tok)
- `test_fake_pix_provider.py` — test_create_charge_anchors_expiry_to_due_date_plus_validity_days_in_brt, test_verify_webhook_accepts (~643 tok)
- `test_fipe_chain.py` — test_primary_ok_returns_value, test_primary_fail_fallback_ok, test_cache_hit_skips_provider, test_bo (~1132 tok)
- `test_health.py` — client, test_healthz_returns_ok, test_version_has_expected_keys, test_healthz_returns_postgres_and_r (~526 tok)
- `test_inadimplencia_overdue_amount.py` — test_within_carencia_returns_zero_encargos, test_day_1_past_carencia_applies_multa_and_juros, test_f (~2117 tok)
- `test_inadimplencia_rules.py` — test_multa_pct_above_ceiling_rejected, test_juros_pct_above_ceiling_rejected, test_carencia_dias_abo (~996 tok)
- `test_indicators_endpoints.py` — test_list_indicators_returns_array, test_indicator_series, test_refresh_indicators_requires_admin, t (~993 tok)
- `test_indicators_service.py` — test_upsert_and_latest, test_upsert_idempotent, test_series_returns_ordered_points, test_series_inva (~1499 tok)
- `test_maildir.py` — test_deliver_writes_eml_file (~122 tok)
- `test_main_pix_startup.py` — test_pix_sandbox_warning_fires_for_efi_sandbox_in_production, test_pix_sandbox_warning_silent_outsid (~277 tok)
- `test_models.py` — test_all_phase1_models_importable_and_tables_exist, test_all_phase2_models_importable_and_tables_exi (~834 tok)
- `test_notification_service.py` — Integration tests for NotificationService.enqueue() — DB only, no SMTP. (~846 tok)
- `test_notification_templates.py` — Tests that every template key renders without error and contains expected strings. (~1024 tok)
- `test_parcela_service.py` — setup, test_list_for_customer_returns_proposals, test_get_schedule_returns_parcelas, test_cannot_acc (~1698 tok)
- `test_pix_deps.py` — _FakeEfiProvider: test_external_provider_value_no_longer_supported, test_efi_provider_requires_setti (~618 tok)
- `test_pix_protocol.py` — test_payer_info_fields, test_create_charge_uses_date_based_due_date_and_validity_days, test_create_c (~349 tok)
- `test_pix_service_inadimplencia.py` — Integration tests for _ensure_charge overdue regeneration logic. (~1896 tok)
- `test_pix_service_smoke.py` — Smoke test — full PixService tests are in test_pix_service.py (Plan 6E). (~63 tok)
- `test_pix_service.py` — pix_setup, test_ensure_charge_builds_payer_info_from_linked_client, test_ensure_charge_threads_due_d (~2305 tok)
- `test_portal_endpoints_smoke.py` — Smoke tests for portal API — full isolation tests are in test_portal_endpoints.py (Plan 6E). (~546 tok)
- `test_proposal_endpoints.py` — Integration tests for proposal API endpoints. (~1505 tok)
- `test_proposal_phase6.py` — Tests for Phase 6 ProposalService changes: invite on approve, cancel with cleanup. (~1302 tok)
- `test_proposal_service_unit.py` — Unit tests for ProposalService using mocked session + arq. (~785 tok)
- `test_proposal_service.py` — Integration tests for ProposalService against a real Postgres. (~2401 tok)
- `test_proposal_snapshot.py` — test_build_snapshot_basic, test_build_snapshot_tarifas_computed, test_snapshot_rejects_extra_fields, (~1010 tok)
- `test_render_tasks.py` — Worker render task tests — WeasyPrint is mocked. (~1147 tok)
- `test_rules_update.py` — test_update_changes_value_and_writes_audit, test_update_with_motivo_stored_in_diff, test_update_publ (~949 tok)
- `test_schemas.py` — M: test_decimal_str_serializes_as_string, test_decimal_str_parses_from_string, test_simulation_creat (~552 tok)
- `test_settings_service.py` — clean_settings, test_get_all_returns_env_defaults_when_table_empty, test_update_and_get_round_trip, (~596 tok)
- `test_settings.py` — test_settings_loads_with_valid_env, test_settings_missing_database_url_raises, test_settings_has_jwt (~425 tok)
- `test_simulation_endpoints.py` — test_get_business_rules, test_preview_returns_schedule, test_create_simulation_returns_201, test_lis (~2167 tok)
- `test_simulation_service.py` — tenant, user, rules_seeded, client_and_vehicle (~3377 tok)
- `test_storage_contract.py` — Storage backend contract test — same assertions pass both Local and S3 (MinIO). (~590 tok)
- `test_storage_local.py` — storage, test_put_and_get, test_signed_url_structure, test_signed_url_valid_hmac (~588 tok)
- `test_tenant_isolation.py` — two_tenants, test_get_users_returns_only_own_tenant, test_get_me_returns_own_tenant, test_patch_user (~1047 tok)
- `test_users_endpoints.py` — setup, test_get_me, test_get_users_as_admin_returns_staff_only, test_get_users_as_user_role_returns_ (~963 tok)
- `test_vehicle_endpoints.py` — test_create_and_list_vehicles, test_set_vehicle_status, test_invalid_status_transition_returns_422 (~734 tok)
- `test_vehicle_service.py` — ctx_and_session, test_create_vehicle_defaults_to_ativo, test_set_status_ativo_to_reservado, test_set (~977 tok)
- `test_worker_integration.py` — test_ping_job_enqueue_and_process (~260 tok)
- `test_worker.py` — test_ping_returns_pong (~69 tok)

## design-system/financialsim/

- `MASTER.md` — Design System Master File (~1286 tok)

## design-system/kraken/

- `DESIGN.md` — Design System Inspired by Kraken (~1129 tok)

## design-system/notion/

- `DESIGN.md` — Overview (~5642 tok)

## docs/

- `ARQUITETURA.md` — Arquitetura (~198 tok)
- `guia_usuario.md` — Guia do usuario (~416 tok)
- `INSTALACAO.md` — Instalacao do FinacialSim (~384 tok)
- `matematica_price.md` — Matematica financeira do FinacialSim (~454 tok)
- `todo.md` — TODO List (~1039 tok)
- `troubleshooting.md` — Troubleshooting (~330 tok)

## docs/adr/

- `0001-pix-cobranca-automatica-always-send-reminder.md` — Always send the due-soon reminder regardless of cobrança-automática charge-generation outcome (~668 tok)
- `0002-overdue-charge-daily-regeneration.md` — ADR-0002 — Overdue CobV charges regenerated daily (not stored-rate comparison) (~593 tok)

## docs/agents/

- `domain.md` — Domain Docs (~485 tok)
- `efi-pix-setup.md` — Efí Pix provider setup (~992 tok)
- `issue-tracker.md` — Issue tracker: GitHub (~271 tok)
- `triage-labels.md` — Triage Labels (~265 tok)

## docs/deploy/

- `cloud.md` — Deploy: AWS ECS + RDS + S3 (~336 tok)
- `docker-compose.md` — Deploy: Single VPS with Docker Compose + Caddy (~526 tok)

## docs/prompts/

- `pix.md` — Contexto (~447 tok)
- `saas.md` — Context (~377 tok)

## docs/runbook/

- `incidents.md` — Incident Runbook — FinacialSim SaaS (~1379 tok)

## docs/superpowers/plans/

- `2026-05-28-saas-phase-0-foundations.md` — Phase 0 — Foundations Implementation Plan (~13678 tok)
- `2026-05-29-saas-phase-1-auth-rbac.md` — Phase 1 — Auth + RBAC + Tenant Management Implementation Plan (~23789 tok)
- `2026-05-30-saas-phase-2-backend.md` — Phase 2 — Simulação Backend Implementation Plan (~22074 tok)
- `2026-05-30-saas-phase-2-frontend.md` — Phase 2 — Simulação Frontend Implementation Plan (~13709 tok)
- `2026-05-30-saas-phase-3-backend.md` — Phase 3 — Cadastros Backend Implementation Plan (~22033 tok)
- `2026-05-30-saas-phase-3-frontend.md` — Phase 3 — Cadastros Frontend Implementation Plan (~16195 tok)
- `2026-06-01-saas-phase-4-backend.md` — Phase 4 Backend — Indicadores + Business Rules + Scheduler + Audit Log (~22683 tok)
- `2026-06-01-saas-phase-4-frontend.md` — Phase 4 Frontend — Indicadores + Business Rules Editor + Audit Log (~8767 tok)
- `2026-06-01-saas-phase-5a-foundations.md` — Phase 5A — Foundations Implementation Plan (~7934 tok)
- `2026-06-01-saas-phase-5b-services.md` — Phase 5B — Services + Worker + API Implementation Plan (~11760 tok)
- `2026-06-01-saas-phase-5c-tests.md` — Phase 5C — Integration Tests Implementation Plan (~6063 tok)
- `2026-06-01-saas-phase-5d-frontend.md` — Phase 5D — Frontend Implementation Plan (~5184 tok)
- `2026-06-02-saas-phase-6-index.md` — Phase 6 — Portal do Cliente + Pix Scaffold — Plan Index (~1126 tok)
- `2026-06-02-saas-phase-6a-data-pix.md` — Phase 6A — Data Layer + Pix Module Implementation Plan (~5095 tok)
- `2026-06-02-saas-phase-6b-services.md` — Phase 6B — Services Implementation Plan (~12284 tok)
- `2026-06-02-saas-phase-6c-api.md` — Phase 6C — API Endpoints + Worker Cron Implementation Plan (~5061 tok)
- `2026-06-02-saas-phase-6d-frontend.md` — Phase 6D — Frontend Portal Implementation Plan (~6999 tok)
- `2026-06-02-saas-phase-6e-tests.md` — Phase 6E — Tests Implementation Plan (~7715 tok)
- `2026-06-02-saas-phase-7-index.md` — Phase 7 — Notificações + Polish — Plan Index (~1024 tok)
- `2026-06-02-saas-phase-7a-data.md` — Phase 7A — Data Layer Implementation Plan (~2682 tok)
- `2026-06-02-saas-phase-7b-notification-service.md` — Phase 7B — Notification Service + Templates Implementation Plan (~6203 tok)
- `2026-06-02-saas-phase-7c-worker.md` — Phase 7C — Worker + Wiring Implementation Plan (~7258 tok)
- `2026-06-02-saas-phase-7d-observability.md` — Phase 7D — Observability Implementation Plan (~2074 tok)
- `2026-06-02-saas-phase-7e-cli.md` — Phase 7E — CLI Implementation Plan (~2400 tok)
- `2026-06-02-saas-phase-7f-ux-polish.md` — Phase 7F — UX Polish Implementation Plan (~2567 tok)
- `2026-06-02-saas-phase-7g-docs.md` — Phase 7G — Documentation Implementation Plan (~2818 tok)
- `2026-06-03-admin-dashboard.md` — Admin Dashboard Implementation Plan (~16492 tok)
- `2026-06-03-setup-tenant-script.md` — Setup Tenant Script Implementation Plan (~3471 tok)
- `2026-06-04-indicators-bacen-fixes.md` — Indicadores BACEN — Label Fixes + Derived Values Implementation Plan (~4444 tok)
- `2026-06-04-ipva-emplacamento-business-rules.md` — IPVA & Emplacamento — Configurable Business Rules Implementation Plan (~5075 tok)
- `2026-06-07-efi-pix-provider.md` — Efí Pix Provider (Phase 1 — CobV Redesign) Implementation Plan (~1179 tok)
- `2026-06-08-efi-pix-provider-plan-part1.md` — Efí Pix Provider — Part 1: Foundation (Tasks 1–4) (~3854 tok)
- `2026-06-08-efi-pix-provider-plan-part2.md` — Efí Pix Provider — Part 2: Service Layer (Tasks 5–6) (~4869 tok)
- `2026-06-08-efi-pix-provider-plan-part3.md` — Efí Pix Provider — Part 3: EfiPixProvider (Tasks 7–9) (~4304 tok)
- `2026-06-08-efi-pix-provider-plan-part4.md` — Efí Pix Provider — Part 4: Wiring + Runbook (Tasks 10–13) (~5859 tok)
- `2026-06-09-pix-fase3-inadimplencia.md` — Fase 3 — Inadimplência Implementation Plan (~14387 tok)

## docs/superpowers/plans/done/

- `2026-05-23-finacialsim-plan-index.md` — FinacialSim — Implementation Plan Index (~899 tok)
- `2026-05-23-phase-1-core.md` — Phase 1 — Core Financeiro (~13053 tok)
- `2026-05-23-phase-2-data.md` — Phase 2 — Persistência (SQLAlchemy + Alembic) (~13668 tok)
- `2026-05-23-phase-3-integrations.md` — Phase 3 — Integrações FIPE + BACEN (~13690 tok)
- `2026-05-23-phase-4-services.md` — Phase 4 — Serviços (orquestração) (~17783 tok)
- `2026-05-23-phase-5-ui.md` — Phase 5 — UI (NiceGUI + janela nativa) (~14257 tok)
- `2026-05-23-phase-6-pdf-packaging.md` — Phase 6 — PDF, empacotamento e instalação (~10488 tok)
- `2026-05-26-simulacao-smart-defaults.md` — Simulacao Smart Defaults Implementation Plan (~4554 tok)
- `2026-05-26-ui-error-feedback.md` — UI Error Feedback Implementation Plan (~4295 tok)
- `2026-05-26-veiculos.md` — Vehicle Registry Implementation Plan (~19614 tok)
- `2026-05-27-ui-polish.md` — UI Polish Implementation Plan (~3826 tok)

## docs/superpowers/specs/

- `2026-05-28-saas-phase-0-foundations.md` — Phase 0 — Foundations (~1112 tok)
- `2026-05-28-saas-phase-1-auth-rbac.md` — Phase 1 — Auth + RBAC + Tenant management (~2091 tok)
- `2026-05-28-saas-phase-2-simulacao.md` — Phase 2 — Core domain port + Simulação (~1888 tok)
- `2026-05-28-saas-phase-3-cadastros.md` — Phase 3 — Cadastros (Clientes + Veículos + FIPE) (~1149 tok)
- `2026-05-28-saas-phase-4-indicadores-rules.md` — Phase 4 — Indicadores + Business Rules UI + Scheduler + Audit log (~1212 tok)
- `2026-05-28-saas-phase-5-propostas-pdf.md` — Phase 5 — Propostas + PDF/Carnê (worker-rendered) (~2010 tok)
- `2026-05-28-saas-phase-6-portal-cliente-pix.md` — Phase 6 — Portal do cliente + Pix scaffold (~3512 tok)
- `2026-05-28-saas-phase-7-notificacoes.md` — Phase 7 — Notificações (email) + polish (~1360 tok)
- `2026-05-28-saas-roadmap.md` — FinacialSim SaaS — Master Roadmap (~4042 tok)
- `2026-06-03-admin-dashboard-design.md` — Admin Dashboard — Design Spec (~2194 tok)
- `2026-06-03-setup-tenant-script.md` — Setup Tenant Script — Design Spec (~1039 tok)
- `2026-06-04-indicators-bacen-fixes.md` — Indicadores BACEN — Label Fixes + Derived Values — Design Spec (~1334 tok)
- `2026-06-04-ipva-emplacamento-business-rules.md` — IPVA & Emplacamento — Configurable Business Rules (~1918 tok)
- `2026-06-07-02-pix-cobranca-automatica-design.md` — Pix — Phase 2 (Cobrança automática) (~4564 tok)
- `2026-06-07-efi-pix-provider-design.md` — Efí Pix Provider — Phase 1 (PIX básico real, fundação CobV) (~10291 tok)
- `2026-06-07-pix-cobranca-automatica-design.md` — Pix — Phase 2 (Cobrança automática) (~6638 tok)
- `2026-06-09-pix-fase3-inadimplencia-design.md` — Pix — Fase 3 (Inadimplência) (~4929 tok)

## docs/superpowers/specs/done/

- `2026-05-23-finacialsim-design.md` — FinacialSim — Design Spec (~13774 tok)
- `2026-05-26-simulacao-smart-defaults-design.md` — Design Spec — Simulacao Smart Defaults (~1600 tok)
- `2026-05-26-ui-error-feedback-design.md` — Design Spec — UI Error Feedback for Simulation & Vehicle Flows (~1864 tok)
- `2026-05-26-veiculos-design.md` — Design Spec — Cadastro de Veículos (~3643 tok)
- `2026-05-27-carne-design.md` — Design Spec — Geração de Carnê PDF (~995 tok)
- `2026-05-27-ui-polish-design.md` — Design Spec — UI Polish: Login, Cadastro, Simulação, Configurações (~2273 tok)
- `2026-05-28-ipva-emplacamento-auto-calc-design.md` — Design Spec — IPVA & Emplacamento Auto-Calculation (~1117 tok)

## frontend/

- `.dockerignore` (~7 tok)
- `index.html` — FinacialSim (~210 tok)
- `package.json` — Node.js package manifest (~316 tok)
- `tailwind.config.ts` — /*.{ts,tsx}"], (~50 tok)
- `tsconfig.app.json` (~187 tok)
- `vite.config.ts` (~154 tok)

## frontend/src/

- `App.tsx` — queryClient (~923 tok)
- `index.css` — Styles: 1 rules (~7 tok)

## frontend/src/components/

- `EditableField.tsx` — EditableField (~1441 tok)
- `FormErrorSummary.tsx` — FormErrorSummary (~197 tok)
- `RequireRole.tsx` — RequireRole (~178 tok)

## frontend/src/components/ui/

- `badge.tsx` — badgeVariants (~316 tok)
- `button.tsx` — buttonVariants (~420 tok)
- `collapsible.tsx` — Collapsible (~91 tok)
- `dialog.tsx` — Dialog — renders modal (~747 tok)
- `input.tsx` — Input (~226 tok)
- `label.tsx` — labelVariants (~200 tok)
- `select.tsx` — Select (~879 tok)
- `slider.tsx` — Slider (~298 tok)
- `switch.tsx` — Switch (~320 tok)

## frontend/src/context/

- `AuthContext.tsx` — AuthContext (~574 tok)

## frontend/src/hooks/

- `useBusinessRules.ts` — Exports useBusinessRules, suggestRate (~222 tok)
- `useSimulationPreview.ts` — Exports useSimulationPreview (~438 tok)

## frontend/src/lib/

- `admin-settings.ts` — API routes: PUT (1 endpoints) (~124 tok)
- `api.ts` — In dev: Vite proxy forwards /api/* → http://localhost:8000/* (~697 tok)
- `audit-log.ts` — Exports AuditLogItem, AuditLogPage, AuditLogParams, listAuditLog (~179 tok)
- `cep.ts` — Exports CepResult, lookupCep (~113 tok)
- `clients.ts` — Exports ClientOut, ClientListPage, ClientIn, listClients + 4 more (~503 tok)
- `csv.ts` — Exports buildCsv, downloadCsv (~212 tok)
- `decimal.ts` — Exports fmtBRL, fmtPct, fmtRate, parseBRL (~225 tok)
- `fipe.ts` — Exports FipeBrand, FipeModel, FipeYear, FipePrice + 4 more (~380 tok)
- `proposals.ts` — Exports ProposalOut, ProposalListItem, ProposalListPage, createProposal + 6 more (~596 tok)
- `utils.ts` — Exports cn (~49 tok)
- `vehicles.ts` — Exports VehicleOut, VehicleListPage, VehicleIn, listVehicles + 4 more (~583 tok)

## frontend/src/routes/

- `ForgotPassword.tsx` — schema — renders form (~714 tok)
- `Health.tsx` — Health (~162 tok)
- `Index.tsx` — decodeRole (~995 tok)
- `Login.tsx` — schema — renders form (~874 tok)
- `ResetPassword.tsx` — schema — renders form (~853 tok)
- `Simulacao.tsx` — Simulacao (~789 tok)
- `SimulacaoEdit.tsx` — isoToDateStr (~3650 tok)

## frontend/src/routes/admin/

- `AdminLayout.tsx` — NAV_ITEMS (~634 tok)
- `AuditLog.tsx` — ACAO_OPTIONS — renders table (~1546 tok)
- `BusinessRules.tsx` — fetchRules — renders table (~3669 tok)
- `Indicators.tsx` — LABELS (~1155 tok)
- `PixSettings.tsx` — Query getAdminSettings, display pix_provider + pix_webhook_secret (env-only, read-only) (~270 tok)
- `SmtpSettings.tsx` — EMAIL_PROVIDERS (~670 tok)
- `SystemHealth.tsx` — Query /v1/admin/health (refetch 30s), StatusPill component, display postgres/redis + providers with latency/error (~420 tok)
- `Users.tsx` — ── Types ──────────────────────────────────────────────────────────────────── (~4016 tok)

## frontend/src/routes/clientes/

- `ClientesPage.tsx` — isValidCpf — renders form (~4705 tok)

## frontend/src/routes/propostas/

- `PropostasPage.tsx` — STATUS_OPTIONS — renders table (~1428 tok)

## frontend/src/routes/simulacao/

- `ResultCards.tsx` — Card (~516 tok)
- `ScheduleTable.tsx` — CSV_HEADERS — renders table (~742 tok)
- `SimulacaoCharts.tsx` — SimulacaoCharts (~970 tok)
- `SimulacaoForm.tsx` — schema — renders form (~6862 tok)
- `types.ts` — Exports RateCurvePoint, BusinessRules, FeeInput, ExtraInput + 6 more (~917 tok)

## frontend/src/routes/veiculos/

- `FipeCascadePicker.tsx` — selectClass (~1854 tok)
- `VeiculosPage.tsx` — TIPOS — renders form, modal (~4527 tok)

## frontend/src/tests/

- `App.test.tsx` — Wrapper (~278 tok)
- `setup.ts` — jsdom doesn't implement ResizeObserver (used by Recharts/Radix) (~71 tok)
- `simulacao-preview.test.ts` — Declares payload (~354 tok)
- `simulacao.test.tsx` — Wrapper (~794 tok)
- `utils.test.ts` — Declares csv (~412 tok)
- `veiculos.test.tsx` — makeWrapper (~420 tok)

## graphify-out/

- `.graphify_chunk_01.json` (~12050 tok)
- `.graphify_chunk_02.json` (~11748 tok)
- `.graphify_chunk_03.json` (~15290 tok)
- `.graphify_chunk_04.json` — Declares text (~11052 tok)
- `.graphify_chunk_05.json` (~8890 tok)

## ops/

- `Caddyfile` (~31 tok)
- `docker-compose.yml` — Docker Compose services (~704 tok)
- `Dockerfile.api` (~164 tok)
- `Dockerfile.web` (~71 tok)
- `Dockerfile.worker` (~276 tok)
- `nginx.conf` (~39 tok)

## packages/finacialsim_core/

- `pyproject.toml` (~145 tok)

## packages/finacialsim_core/finacialsim_core/

- `__init__.py` — Pure financial math library — no SQLAlchemy, no NiceGUI. (~18 tok)

## packages/finacialsim_core/finacialsim_core/integrations/

- `http.py` — Shared HTTP helper and tenacity callback for all providers. (~215 tok)

## packages/finacialsim_core/finacialsim_core/integrations/fipe/

- `brasilapi.py` — FIPE BrasilAPI fallback provider. (~737 tok)
- `manual.py` — Manual FIPE provider — constructs a VehicleQuote from operator-supplied input. (~460 tok)
- `parallelum.py` — FIPE Parallelum primary provider. (~980 tok)

## scripts/

- `sync_core.py` — Sync finacialsim_core from the desktop repo. (~862 tok)
