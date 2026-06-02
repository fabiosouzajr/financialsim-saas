# Incident Runbook — FinacialSim SaaS

> Last updated: 2026-06-02. Update after every incident.

---

## Scenario 1: Pix Outage

**Symptoms:**
- `POST /portal/financiamentos/{id}/pix` returns 503 or times out
- Logs show `pix_provider` errors

**Diagnosis:**
```bash
# Count pending Pix charges
psql $DATABASE_URL -c "SELECT status, count(*) FROM pix_charges GROUP BY status;"

# Check provider health
psql $DATABASE_URL -c "SELECT * FROM provider_health ORDER BY checked_at DESC LIMIT 5;"
```

**Resolution:**
1. If `PIX_PROVIDER=fake` — verify env var is set correctly for the target environment
2. If external PSP is down:
   - Portal returns user-friendly 503 ("Pix temporarily unavailable")
   - No action required until PSP recovers
   - Existing `pending` charges remain; customer can retry via portal
3. Once PSP recovers, customers retry — `create_charge_for_parcela` is idempotent
4. If charges stuck `pending` > 30 min, manually expire:
   ```sql
   UPDATE pix_charges SET status = 'expired', atualizado_em = now()
   WHERE status = 'pending' AND expires_at < now();
   ```

**Post-incident:** Alert when `pix_charges` with `status=pending` exceed 50 rows for > 30 min.

---

## Scenario 2: BACEN Degraded

**Symptoms:**
- `/api/indicators` returns stale data (last update > 24h ago)
- Worker logs show `update_bacen_indicators: primary failed, trying fallback`

**Diagnosis:**
```bash
# Check last indicator sync
psql $DATABASE_URL -c "
  SELECT codigo, MAX(data) as latest_data, MAX(created_at) as last_synced
  FROM indicators_history GROUP BY codigo ORDER BY codigo;
"

# Check provider health
psql $DATABASE_URL -c "
  SELECT provider, healthy, checked_at FROM provider_health
  WHERE provider IN ('bacen_sgs', 'bacen_brasilapi')
  ORDER BY checked_at DESC LIMIT 4;
"
```

**Resolution:**
1. Stale indicators are non-critical — simulations use last known rates
2. Daily job retries automatically with idempotency key (one run per day)
3. Manually re-trigger if both providers were down:
   ```bash
   docker compose exec api python -c "
   import asyncio, arq
   from finacialsim_saas.workers.worker import get_redis_settings
   async def main():
       pool = await arq.create_pool(get_redis_settings())
       await pool.enqueue_job('update_bacen_indicators')
       await pool.aclose()
   asyncio.run(main())
   "
   ```
4. If both providers down > 24h, manually insert from BACEN website:
   ```sql
   INSERT INTO indicators_history (tenant_id, codigo, valor, unidade, data)
   VALUES (NULL, 'SELIC', 10.50, '%', CURRENT_DATE)
   ON CONFLICT DO NOTHING;
   ```

**Post-incident:** Alert on `MAX(indicators_history.data)` age > 48h.

---

## Scenario 3: Email Outage (Notifications Pile-Up)

**Symptoms:**
- Customers not receiving emails
- `notifications_outbox` rows accumulating in `pending` status
- Drain job logs: `smtp failure, will retry`

**Diagnosis:**
```bash
# Count by status
psql $DATABASE_URL -c "SELECT status, COUNT(*) FROM notifications_outbox GROUP BY status;"

# Recent errors
psql $DATABASE_URL -c "
  SELECT id, template_key, attempts, last_error, updated_at
  FROM notifications_outbox
  WHERE status IN ('pending', 'deadlettered')
  ORDER BY updated_at DESC LIMIT 20;
"
```

**Resolution — short outage (< 1h):**
1. No action needed — backoff retries resume when SMTP recovers
2. Monitor: `SELECT COUNT(*) FROM notifications_outbox WHERE status='pending'`

**Resolution — wrong credentials or long outage:**
1. Fix SMTP credentials: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` in env
2. Restart worker: `docker compose restart worker`
3. Force immediate drain (bypasses Redis lock):
   ```bash
   docker compose exec api finacialsim-saas notifications drain
   ```

**Resolution — deadlettered rows:**
1. Fix SMTP issue first
2. Retry individual rows:
   ```bash
   psql $DATABASE_URL -c "SELECT id FROM notifications_outbox WHERE status='deadlettered';"
   docker compose exec api finacialsim-saas notifications retry --outbox-id <uuid>
   ```
3. Or bulk-reset:
   ```sql
   UPDATE notifications_outbox
   SET status = 'pending', attempts = 0, last_error = NULL,
       scheduled_for = now(), updated_at = now()
   WHERE status = 'deadlettered';
   ```
   Then: `docker compose exec api finacialsim-saas notifications drain`

**Post-incident:** Alert when > 100 `pending` rows for > 15 min.

---

## Scenario 4: Deadletter Pile-Up

**Symptoms:**
- Many `deadlettered` rows in `notifications_outbox`
- Customers report missing emails of a specific type

**Diagnosis:**
```bash
psql $DATABASE_URL -c "
  SELECT template_key, COUNT(*), MAX(last_error) as last_error
  FROM notifications_outbox
  WHERE status = 'deadlettered'
  GROUP BY template_key ORDER BY count DESC;
"
```

**Root causes and fixes:**

| Root Cause | Fix |
|------------|-----|
| SMTP credentials wrong | Fix env vars, restart worker, bulk-retry (see Scenario 3) |
| Template rendering error (bad payload) | Fix template, deploy, bulk-retry. Check `last_error` for `UndefinedError`. |
| `target_email` is NULL | Bug in trigger site — fix code and re-enqueue manually |
| Template key typo | Fix code, deploy, bulk-retry |

**Manual re-enqueue:**
```bash
docker compose exec api finacialsim-saas notifications retry --outbox-id <uuid>
```

**Verify delivery after retry:**
- Dev: check Mailpit at `http://localhost:8025`
- Prod: check provider dashboard (SES console, Resend dashboard)

**Post-incident:** If template rendering failed, add the case to `tests/test_notification_templates.py`.
