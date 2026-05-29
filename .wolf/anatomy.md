# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-05-29T19:21:31.391Z
> Files: 120 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.gitignore` — Git ignore rules (~1044 tok)
- `CLAUDE.md` — CLAUDE.md (~1980 tok)
- `pyproject.toml` (~34 tok)
- `README.md` — Project documentation (~461 tok)

## .claude/

- `settings.json` (~441 tok)
- `settings.local.json` (~34 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .github/workflows/

- `ci.yml` — CI: CI (~573 tok)

## backend/

- `pyproject.toml` (~285 tok)

## backend/alembic/

- `env.py` — get_url, run_migrations_offline, do_run_migrations, run_async_migrations (~421 tok)

## backend/alembic/versions/

- `001_create_tenants.py` — create tenants table (~240 tok)
- `002_auth_tables.py` — auth tables — users, password_reset_tokens, refresh_tokens, audit_log, notifications_outbox (~1533 tok)

## backend/finacialsim_saas/

- `__init__.py` — FinacialSim SaaS backend. (~10 tok)
- `errors.py` — Declares AppError (~368 tok)
- `main.py` — Shared state accessed by route handlers — populated during lifespan startup (~731 tok)
- `settings.py` — Settings: jwt_secret_key, access_token_expire_minutes, refresh_token_expire_days, frontend_base_url, maildir_path (~310 tok)

## backend/finacialsim_saas/api/

- `auth.py` — API: 5 endpoints (~820 tok)
- `health.py` — API: 2 endpoints (~289 tok)
- `users.py` — API: 4 endpoints (~1258 tok)

## backend/finacialsim_saas/auth/

- `__init__.py` (~0 tok)
- `deps.py` — from: get_db_session, get_current_ctx, require_role (~738 tok)
- `schemas.py` — Declares LoginRequest (~267 tok)
- `service.py` — AuthService: register_user, authenticate, issue_tokens, rotate_refresh + 4 more (~2052 tok)

## backend/finacialsim_saas/cli/

- `__init__.py` (~0 tok)
- `main.py` — tenant_create, user_create, user_reset_password (~1113 tok)

## backend/finacialsim_saas/data/

- `database.py` — Base: build_engine, build_session_factory, check_db (~252 tok)
- `models.py` — ORM models: Tenant, User, PasswordResetToken, RefreshToken, AuditLog, NotificationsOutbox; Role enum (~320 tok)

## backend/finacialsim_saas/middleware/

- `logging.py` — configure_logging (~153 tok)

## backend/finacialsim_saas/workers/

- `maildir.py` — MaildirChannel: deliver, drain_outbox (~753 tok)
- `tasks.py` — ping (~60 tok)
- `worker.py` — WorkerSettings: get_redis_settings (~130 tok)

## backend/tests/

- `conftest.py` — ── Postgres ────────────────────────────────────────────────────────────────── (~779 tok)
- `test_auth_endpoints.py` — seed, test_login_returns_tokens, test_login_wrong_password_returns_401, test_refresh_returns_new_tok (~850 tok)
- `test_auth_service.py` — tenant, test_register_and_authenticate, test_authenticate_wrong_password_raises, test_issue_tokens_r (~1184 tok)
- `test_cli.py` — runner, test_tenant_create_and_user_create (~270 tok)
- `test_database.py` — test_db_ping, test_session_can_execute_query (~124 tok)
- `test_deps.py` — test_parse_bearer_valid_token, test_parse_bearer_no_header_returns_none, test_require_role_wrong_rol (~607 tok)
- `test_errors.py` — test_not_found_code_and_status, test_external_provider_degraded_flag, test_all_six_errors_are_app_er (~255 tok)
- `test_health.py` — client, test_healthz_returns_ok, test_version_has_expected_keys, test_app_error_handler_returns_stru (~429 tok)
- `test_maildir.py` — test_deliver_writes_eml_file (~122 tok)
- `test_models.py` — test_all_phase1_models_importable_and_tables_exist (~145 tok)
- `test_settings.py` — test_settings_loads_with_valid_env, test_settings_missing_database_url_raises, test_settings_has_jwt (~329 tok)
- `test_tenant_isolation.py` — two_tenants, test_get_users_returns_only_own_tenant, test_get_me_returns_own_tenant, test_patch_user (~1047 tok)
- `test_users_endpoints.py` — setup, test_get_me, test_get_users_as_admin_returns_staff_only, test_get_users_as_user_role_returns_ (~963 tok)
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

## docs/agents/

- `domain.md` — Domain Docs (~485 tok)
- `issue-tracker.md` — Issue tracker: GitHub (~271 tok)
- `triage-labels.md` — Triage Labels (~265 tok)

## docs/prompts/

- `pix.md` — Contexto (~447 tok)
- `saas.md` — Context (~377 tok)

## docs/superpowers/plans/

- `2026-05-28-saas-phase-0-foundations.md` — Phase 0 — Foundations Implementation Plan (~13678 tok)
- `2026-05-29-saas-phase-1-auth-rbac.md` — Phase 1 — Auth + RBAC + Tenant Management Implementation Plan (~23789 tok)

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
- `2026-05-28-saas-phase-2-simulacao.md` — Phase 2 — Core domain port + Simulação (~1590 tok)
- `2026-05-28-saas-phase-3-cadastros.md` — Phase 3 — Cadastros (Clientes + Veículos + FIPE) (~1149 tok)
- `2026-05-28-saas-phase-4-indicadores-rules.md` — Phase 4 — Indicadores + Business Rules UI + Scheduler + Audit log (~1212 tok)
- `2026-05-28-saas-phase-5-propostas-pdf.md` — Phase 5 — Propostas + PDF/Carnê (worker-rendered) (~2010 tok)
- `2026-05-28-saas-phase-6-portal-cliente-pix.md` — Phase 6 — Portal do cliente + Pix scaffold (~1730 tok)
- `2026-05-28-saas-phase-7-notificacoes.md` — Phase 7 — Notificações (email) + polish (~1360 tok)
- `2026-05-28-saas-roadmap.md` — FinacialSim SaaS — Master Roadmap (~4042 tok)

## docs/superpowers/specs/done/

- `2026-05-23-finacialsim-design.md` — FinacialSim — Design Spec (~13774 tok)
- `2026-05-26-simulacao-smart-defaults-design.md` — Design Spec — Simulacao Smart Defaults (~1600 tok)
- `2026-05-26-ui-error-feedback-design.md` — Design Spec — UI Error Feedback for Simulation & Vehicle Flows (~1864 tok)
- `2026-05-26-veiculos-design.md` — Design Spec — Cadastro de Veículos (~3643 tok)
- `2026-05-27-carne-design.md` — Design Spec — Geração de Carnê PDF (~995 tok)
- `2026-05-27-ui-polish-design.md` — Design Spec — UI Polish: Login, Cadastro, Simulação, Configurações (~2273 tok)
- `2026-05-28-ipva-emplacamento-auto-calc-design.md` — Design Spec — IPVA & Emplacamento Auto-Calculation (~1117 tok)

## frontend/

- `package.json` — Node.js package manifest (~316 tok)
- `tailwind.config.ts` — /*.{ts,tsx}"], (~50 tok)
- `tsconfig.app.json` (~187 tok)
- `vite.config.ts` (~170 tok)

## frontend/src/

- `App.tsx` — queryClient (~438 tok)
- `index.css` — Styles: 1 rules (~7 tok)

## frontend/src/components/

- `RequireRole.tsx` — RequireRole (~178 tok)

## frontend/src/context/

- `AuthContext.tsx` — AuthContext (~574 tok)

## frontend/src/lib/

- `api.ts` — In dev: Vite proxy forwards /api/* → http://localhost:8000/* (~697 tok)

## frontend/src/routes/

- `ForgotPassword.tsx` — schema — renders form (~687 tok)
- `Health.tsx` — Health (~162 tok)
- `Index.tsx` — Index (~87 tok)
- `Login.tsx` — schema — renders form (~844 tok)
- `ResetPassword.tsx` — schema — renders form (~827 tok)

## frontend/src/routes/admin/

- `Users.tsx` — AdminUsers — renders table (~568 tok)

## frontend/src/tests/

- `App.test.tsx` — Wrapper (~202 tok)
- `setup.ts` (~11 tok)

## graphify-out/

- `.graphify_chunk_01.json` (~12050 tok)
- `.graphify_chunk_02.json` (~11748 tok)
- `.graphify_chunk_03.json` (~15290 tok)
- `.graphify_chunk_04.json` — Declares text (~11052 tok)
- `.graphify_chunk_05.json` (~8890 tok)

## ops/

- `Caddyfile` (~39 tok)
- `docker-compose.yml` — Docker Compose services (~566 tok)
- `Dockerfile.api` (~148 tok)
- `Dockerfile.web` (~71 tok)
- `Dockerfile.worker` (~257 tok)
- `nginx.conf` (~39 tok)

## packages/finacialsim_core/

- `pyproject.toml` (~145 tok)

## packages/finacialsim_core/finacialsim_core/

- `__init__.py` — Pure financial math library — no SQLAlchemy, no NiceGUI. (~18 tok)

## scripts/

- `sync_core.py` — Sync finacialsim_core from the desktop repo. (~687 tok)
