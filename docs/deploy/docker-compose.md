# Deploy: Single VPS with Docker Compose + Caddy

> Reference deploy for a single Linux VPS. Uses the `ops/` directory artifacts.

## Prerequisites

- Docker + Docker Compose plugin installed
- Domain name pointing to the VPS IP
- Ports 80 and 443 open

## Services

See [`ops/docker-compose.yml`](../../ops/docker-compose.yml) for the full service definition:

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
APP_ENV=production

# Email (Mailpit for local dev, SMTP for prod)
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=<resend api key>
SMTP_TLS=true
SMTP_FROM=noreply@yourdomain.com
```

## Caddy Auto-TLS

Edit [`ops/Caddyfile`](../../ops/Caddyfile) and replace the placeholder domain with your domain.

## First Deploy

```bash
git clone <repo> && cd financialsim-saas
cp .env.example .env && nano .env
docker compose -f ops/docker-compose.yml up -d
```

## Updating

```bash
git pull
docker compose -f ops/docker-compose.yml build
docker compose -f ops/docker-compose.yml up -d
```

The `migrate` service runs Alembic automatically on each `up`.

## Local Dev — Mailpit for Email Testing

Add to `ops/docker-compose.yml` under `services:`:

```yaml
  mailpit:
    image: axllent/mailpit
    ports:
      - "8025:8025"   # web UI
      - "1025:1025"   # SMTP
```

Set `SMTP_HOST=mailpit` in your `.env` to route emails to Mailpit's web UI at `http://localhost:8025`.

## Backups

```bash
docker compose -f ops/docker-compose.yml exec db \
  pg_dump -U finacialsim finacialsim > backup-$(date +%Y%m%d).sql
```

> TODO: Automated backup cron + offsite copy
