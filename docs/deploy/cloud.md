# Deploy: AWS ECS + RDS + S3

> Sketch for a cloud-native deploy. Not yet battle-tested.

## Architecture

```
Route 53 → ALB → ECS Fargate (api, worker, web)
                    ↓
               RDS PostgreSQL 16 (Multi-AZ)
               ElastiCache Redis 7
               S3 (PDF storage)
               SES (email)
```

## ECS Task Definitions

Three tasks:
1. **api** — `ops/Dockerfile.api`, port 8000, env from SSM Parameter Store
2. **worker** — `ops/Dockerfile.worker`, no port (ARQ polling)
3. **web** — `ops/Dockerfile.web`, port 80

## Environment Variables

Same as docker-compose deploy. Source from AWS SSM:
- `DATABASE_URL` — RDS endpoint (use `postgresql+asyncpg://...`)
- `REDIS_URL` — ElastiCache endpoint
- `EMAIL_PROVIDER=ses` (configure IAM role on ECS task for SES)
- `STORAGE_BACKEND=s3`, `STORAGE_S3_BUCKET=<bucket>`

## Migrations

Run as a one-off ECS task before deploying api/worker:

```bash
aws ecs run-task --cluster prod --task-definition finacialsim-api \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-m","alembic","upgrade","head"]}]}'
```

## SES Setup

1. Verify domain in SES
2. Set `EMAIL_PROVIDER=ses`, configure IAM role with `ses:SendEmail`
3. Request production access (lift sandbox)

> TODO: Terraform module, ALB listener rules, ECS service definitions, CloudWatch alarms
