# Phase 7G — Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the full incident runbook (4 scenarios, acceptance-blocking) and create stub deploy docs that reference existing `ops/` artifacts.

**Architecture:** Three markdown files. The runbook is actionable prose per scenario. Deploy docs are stubs with real references to `ops/docker-compose.yml` and `ops/Caddyfile`.

**Depends on:** Nothing — pure documentation

---

## File Map

| Action | File |
|--------|------|
| Create | `docs/runbook/incidents.md` (full) |
| Create | `docs/deploy/docker-compose.md` (stub with real references) |
| Create | `docs/deploy/cloud.md` (stub) |

---

### Task 1: Write the incident runbook

**Files:**
- Create: `docs/runbook/incidents.md`

- [ ] **Step 1: Create full runbook**

```markdown
# Incident Runbook — FinacialSim SaaS

> Last updated: 2026-06-02. Update after every incident.

---

## Scenario 1: Pix Outage

**Symptoms:**
- `POST /portal/financiamentos/{id}/pix` returns 503 or times out
- `PixService.create_charge_for_parcela` throws `ConnectionError` / provider exception
- Logs show `pix_provider` errors

**Diagnosis:**
```bash
# Check recent webhook events
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://app.example.com/api/pix-admin/charges?status=pending | jq '.total'

# Check provider health table
psql $DATABASE_URL -c "SELECT * FROM provider_health ORDER BY checked_at DESC LIMIT 5;"
```

**Resolution:**
1. If `PIX_PROVIDER=fake` — the fake provider is running. Check env var is set correctly for prod.
2. If external PSP is down:
   - The portal returns a user-friendly 503 ("Pix temporarily unavailable")
   - No action required until PSP recovers
   - Existing `pending` Pix charges remain in DB; customer can retry via portal
3. Once PSP recovers, customers retry via portal — `create_charge_for_parcela` is idempotent (returns existing pending charge if one exists)
4. If charges are stuck `pending` for > 30 min, manually expire them:
   ```sql
   UPDATE pix_charges SET status = 'expired', atualizado_em = now()
   WHERE status = 'pending' AND expires_at < now();
   ```

**Post-incident:**
- Add entry to `provider_health` table context in logs
- Consider alerting when `pix_charges` with `status=pending` exceed 50 rows for > 30 min

---

## Scenario 2: BACEN Degraded

**Symptoms:**
- `/api/indicators` returns stale data (last update > 24h ago)
- Worker logs show `update_bacen_indicators: primary failed, trying fallback`
- Both SGS and BrasilAPI returning errors

**Diagnosis:**
```bash
# Check last update time
psql $DATABASE_URL -c "
  SELECT codigo, MAX(data) as latest_data, MAX(created_at) as last_synced
  FROM indicators_history
  GROUP BY codigo
  ORDER BY codigo;
"

# Check provider health
psql $DATABASE_URL -c "
  SELECT provider, healthy, checked_at FROM provider_health
  WHERE provider IN ('bacen_sgs', 'bacen_brasilapi')
  ORDER BY checked_at DESC LIMIT 4;
"
```

**Resolution:**
1. Stale indicators are non-critical — simulations use the last known rates
2. The daily job (`update_bacen_indicators`, 12:00 UTC) retries automatically with a Redis idempotency key per day
3. If the daily job ran but both providers failed, manually re-trigger:
   ```bash
   # Via ARQ (enqueue into Redis)
   cd backend && uv run python -c "
   import asyncio, arq
   from finacialsim_saas.workers.worker import get_redis_settings
   from finacialsim_saas.workers.tasks import update_bacen_indicators
   async def main():
       pool = await arq.create_pool(get_redis_settings())
       await pool.enqueue_job('update_bacen_indicators')
       await pool.aclose()
   asyncio.run(main())
   "
   ```
4. If both providers are down for > 24h, manually insert the latest known SELIC/CDI from BACEN website:
   ```sql
   INSERT INTO indicators_history (tenant_id, codigo, valor, unidade, data)
   VALUES (NULL, 'SELIC', 10.50, '%', CURRENT_DATE)
   ON CONFLICT DO NOTHING;
   ```

**Post-incident:**
- Consider adding a Grafana alert on `MAX(indicators_history.data)` age > 48h

---

## Scenario 3: Email Outage (Notifications Pile-Up)

**Symptoms:**
- Customers not receiving emails
- `notifications_outbox` rows accumulating in `pending` status
- Drain job logs show `smtp failure, will retry`

**Diagnosis:**
```bash
# Count pending/failed rows
psql $DATABASE_URL -c "
  SELECT status, COUNT(*) FROM notifications_outbox
  GROUP BY status ORDER BY status;
"

# Check recent drain job errors
psql $DATABASE_URL -c "
  SELECT id, template_key, attempts, last_error, updated_at
  FROM notifications_outbox
  WHERE status IN ('pending', 'failed', 'deadlettered')
  ORDER BY updated_at DESC LIMIT 20;
"

# Check Mailpit (dev) or SMTP provider (prod) is reachable
curl -s http://localhost:8025/api/v1/info  # Mailpit health
```

**Resolution — short outage (< 1h):**
1. No action needed — backoff retries will resume when SMTP recovers
2. Monitor: `SELECT COUNT(*) FROM notifications_outbox WHERE status='pending'`

**Resolution — long outage or wrong credentials:**
1. Fix SMTP credentials in env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
2. Restart the worker: `docker compose restart worker`
3. Force immediate drain (bypasses Redis lock):
   ```bash
   docker compose exec api finacialsim-saas notifications drain
   ```

**Resolution — deadlettered rows (after 5 failed attempts):**
1. Fix the underlying SMTP issue first
2. Retry each deadlettered row:
   ```bash
   # Get deadlettered row IDs
   psql $DATABASE_URL -c "SELECT id FROM notifications_outbox WHERE status='deadlettered';"

   # Retry each
   docker compose exec api finacialsim-saas notifications retry --outbox-id <uuid>
   ```
3. Or bulk-reset and re-drain:
   ```sql
   UPDATE notifications_outbox
   SET status = 'pending', attempts = 0, last_error = NULL,
       scheduled_for = now(), updated_at = now()
   WHERE status = 'deadlettered';
   ```
   Then: `docker compose exec api finacialsim-saas notifications drain`

**Post-incident:**
- Alert threshold: > 100 `pending` rows for > 15 min → page on-call

---

## Scenario 4: Deadletter Pile-Up

**Symptoms:**
- `notifications_outbox` has many `deadlettered` rows
- Customers complain they never received a specific email type

**Diagnosis:**
```bash
psql $DATABASE_URL -c "
  SELECT template_key, COUNT(*), MAX(last_error) as last_error
  FROM notifications_outbox
  WHERE status = 'deadlettered'
  GROUP BY template_key
  ORDER BY count DESC;
"
```

**Root causes and fixes:**

| Root Cause | Fix |
|-----------|-----|
| SMTP credentials wrong | Fix env vars, restart worker, bulk-retry (see Scenario 3) |
| Template rendering error (bad payload) | Fix template, then retry. Check `last_error` for `UndefinedError`. |
| `target_email` is NULL | Bug in trigger site — fix and re-enqueue manually |
| Template key typo in code | Fix code, deploy, bulk-retry |

**Manual re-enqueue for a specific customer:**
```bash
docker compose exec api finacialsim-saas notifications retry --outbox-id <uuid>
```

**Verify delivery after retry:**
- Dev: check Mailpit at `http://localhost:8025`
- Prod: check provider dashboard (SES console, Resend dashboard)

**Post-incident:**
- Add the root cause to `tasks/lessons.md`
- If template rendering failed, add a smoke test to `test_notification_templates.py`
```

---

### Task 2: Write deploy doc stubs

**Files:**
- Create: `docs/deploy/docker-compose.md`
- Create: `docs/deploy/cloud.md`

- [ ] **Step 1: Create docker-compose.md**

```markdown
# Deploy: Single VPS with Docker Compose + Caddy

> Reference deploy for a single Linux VPS. Uses the `ops/` directory artifacts.
> Tested on: Ubuntu 24.04, Docker 26+

## Prerequisites

- Docker + Docker Compose plugin installed
- Domain name pointing to the VPS IP
- Ports 80 and 443 open

## Services

See `ops/docker-compose.yml` for the full service definition:

- `db` — PostgreSQL 16
- `redis` — Redis 7
- `migrate` — Runs Alembic `upgrade head` on startup
- `api` — FastAPI (uvicorn), port 8000 internal
- `worker` — ARQ worker (cron + task queue)
- `web` — React frontend (nginx), port 80 internal
- `proxy` — Caddy 2 with auto-TLS (ports 80/443 exposed)

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
DATABASE_URL=postgresql+asyncpg://finacialsim:CHANGEME@db:5432/finacialsim
REDIS_URL=redis://redis:6379/0
APP_SECRET_KEY=<random 32 chars>
JWT_SECRET_KEY=<random 32 chars>
STORAGE_HMAC_SECRET=<random 32 chars>
APP_ENV=production

# Email
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=<resend api key>
SMTP_TLS=true
SMTP_FROM=noreply@yourdomain.com

# Pix (production)
PIX_PROVIDER=external
PIX_WEBHOOK_SECRET=<from psp>
```

## Caddy Auto-TLS

Edit `ops/Caddyfile` and replace the placeholder domain:

```caddyfile
app.yourdomain.com {
    reverse_proxy /api/* api:8000
    reverse_proxy /* web:80
}
```

## First Deploy

```bash
git clone ... && cd financialsim-saas
cp .env.example .env && nano .env
docker compose -f ops/docker-compose.yml up -d
```

## Updating

```bash
git pull
docker compose -f ops/docker-compose.yml build
docker compose -f ops/docker-compose.yml up -d
```

The `migrate` service runs automatically on each `up`.

## Backups

```bash
# Manual Postgres backup
docker compose -f ops/docker-compose.yml exec db \
  pg_dump -U finacialsim finacialsim > backup-$(date +%Y%m%d).sql
```

> TODO: Add automated backup cron + offsite copy (S3/R2)
```

- [ ] **Step 2: Create cloud.md**

```markdown
# Deploy: AWS ECS + RDS + S3

> Sketch for a cloud-native deploy. Not yet battle-tested — use as a starting point.

## Architecture

```
Route 53 → ALB → ECS Fargate (api, worker, web)
                    ↓
               RDS PostgreSQL 16 (Multi-AZ)
               ElastiCache Redis 7
               S3 (pdf storage)
               SES (email)
```

## ECS Task Definitions

Three tasks:
1. **api** — `ops/Dockerfile.api`, port 8000, env from SSM Parameter Store
2. **worker** — `ops/Dockerfile.worker`, no port (ARQ polling)
3. **web** — `ops/Dockerfile.web`, port 80

## Environment Variables

Same variables as the docker-compose deploy. Source from AWS SSM:
- `DATABASE_URL` — RDS endpoint
- `REDIS_URL` — ElastiCache endpoint
- `EMAIL_PROVIDER=ses`
- `STORAGE_BACKEND=s3`
- `STORAGE_S3_BUCKET=<bucket name>`

## Migrations

Run as a one-off ECS task before deploying new api/worker tasks:

```bash
aws ecs run-task --cluster prod --task-definition finacialsim-migrate \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","alembic","upgrade","head"]}]}'
```

## SES Setup

1. Verify domain in SES
2. Set `EMAIL_PROVIDER=ses` and configure AWS credentials (IAM role on ECS task)
3. Request production access (SES sandbox lifted)

> TODO: Terraform module, ALB listener rules, ECS service definitions, CloudWatch alarms
```

---

### Task 3: Commit

- [ ] **Step 1: Commit**

```bash
git add docs/runbook/incidents.md docs/deploy/docker-compose.md docs/deploy/cloud.md
git commit -m "docs(phase7g): add incident runbook (4 scenarios) and deploy stubs"
```
