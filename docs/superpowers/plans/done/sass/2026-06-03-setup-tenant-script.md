# Setup Tenant Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `setup-tenant.sh` — a guided, idempotent bash wizard that checks env vars, starts Docker containers, runs migrations, and creates the first tenant + admin user interactively.

**Architecture:** Single bash script at repo root. Delegates all business logic to the existing Typer CLI via `docker compose exec -T api python -m finacialsim_saas.cli.main`. No new Python code required.

**Tech Stack:** Bash, Docker Compose v2, existing Typer CLI (`finacialsim_saas.cli.main`).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `setup-tenant.sh` | Complete wizard script |

---

### Task 1: Scaffold — shebang, helpers, arg parsing

**Files:**
- Create: `setup-tenant.sh`

- [ ] **Step 1: Create the file with scaffold**

```bash
cat > setup-tenant.sh << 'SCRIPT'
#!/usr/bin/env bash
# setup-tenant.sh — FinacialSim SaaS first-tenant setup wizard
#
# Usage:
#   ./setup-tenant.sh                                              # fully interactive
#   ./setup-tenant.sh --name "Acme" --slug acme --admin-email x@x.com

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors (same palette as dev.sh) ───────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}▶${RESET} $*"; }
ok()      { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
die()     { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${RESET}"; }

# ── Arg parsing ───────────────────────────────────────────────────────────────
OPT_NAME=""
OPT_SLUG=""
OPT_EMAIL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)        OPT_NAME="$2";  shift 2 ;;
        --slug)        OPT_SLUG="$2";  shift 2 ;;
        --admin-email) OPT_EMAIL="$2"; shift 2 ;;
        *) die "Unknown option: $1\nUsage: ./setup-tenant.sh [--name NAME] [--slug SLUG] [--admin-email EMAIL]" ;;
    esac
done
SCRIPT
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x setup-tenant.sh
```

- [ ] **Step 3: Verify scaffold parses flags correctly**

```bash
bash -n setup-tenant.sh && echo "syntax OK"
./setup-tenant.sh --bad-flag 2>&1 | grep -q "Unknown option" && echo "bad-flag rejection OK"
```

Expected output:
```
syntax OK
bad-flag rejection OK
```

- [ ] **Step 4: Commit**

```bash
git add setup-tenant.sh
git commit -m "feat: scaffold setup-tenant.sh with helpers and arg parsing"
```

---

### Task 2: Step 1 — Env check

**Files:**
- Modify: `setup-tenant.sh` (append after arg parsing block)

- [ ] **Step 1: Append the env check block**

Add this to the end of `setup-tenant.sh`:

```bash

# ── Step 1: Env check ─────────────────────────────────────────────────────────
section "Step 1/4: Environment check"

if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT/.env"
    set +a
    ok "Loaded .env"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    die "DATABASE_URL is not set.\n\n  Set it in $ROOT/.env or export it before running this script.\n  Example:\n    DATABASE_URL=postgresql+asyncpg://finacialsim:changeme@localhost:5432/finacialsim"
fi

ok "DATABASE_URL is set"
```

- [ ] **Step 2: Verify env check rejects missing DATABASE_URL**

```bash
env -i HOME="$HOME" bash -c '
    cd /tmp
    unset DATABASE_URL
    bash '"$PWD"'/setup-tenant.sh 2>&1 | grep -q "DATABASE_URL is not set" && echo "missing-url rejection OK"
'
```

Expected:
```
missing-url rejection OK
```

- [ ] **Step 3: Verify env check passes with DATABASE_URL set**

```bash
DATABASE_URL="postgresql+asyncpg://x:x@localhost/x" bash -c '
    source setup-tenant.sh 2>&1 | grep -q "DATABASE_URL is set" && echo "env-check passes OK"
' 2>/dev/null || true
# Note: script will continue and hit docker checks — just verify the ok line appears before any docker error
DATABASE_URL="postgresql+asyncpg://x:x@localhost/x" ./setup-tenant.sh 2>&1 | head -5 | grep -q "DATABASE_URL is set" && echo "env-check passes OK"
```

Expected:
```
env-check passes OK
```

- [ ] **Step 4: Commit**

```bash
git add setup-tenant.sh
git commit -m "feat(setup-tenant): step 1 — env check with .env sourcing"
```

---

### Task 3: Step 2 — Container readiness

**Files:**
- Modify: `setup-tenant.sh` (append)

- [ ] **Step 1: Append the container readiness block**

Add this to the end of `setup-tenant.sh`:

```bash

# ── Step 2: Container readiness ───────────────────────────────────────────────
section "Step 2/4: Container readiness"

if ! command -v docker &>/dev/null; then
    die "Docker not found. Install Docker Engine or Docker Desktop:\n  https://docs.docker.com/get-docker/"
fi

cd "$ROOT"

_api_healthy() {
    docker compose ps api 2>/dev/null | grep -q "healthy"
}

if _api_healthy; then
    ok "API container already running and healthy — skipping start"
else
    info "Starting containers (docker compose up -d)..."
    docker compose up -d

    WAIT=0
    until _api_healthy; do
        if [[ $WAIT -ge 60 ]]; then
            die "API container did not become healthy within 60 seconds.\n\n  Check logs: docker compose logs api --tail 30"
        fi
        sleep 3
        WAIT=$((WAIT + 3))
        info "Waiting for API to become healthy... ${WAIT}s"
    done

    ok "API container is healthy"
fi
```

- [ ] **Step 2: Verify docker-not-found message**

```bash
# Temporarily shadow docker with a missing command to test the guard
PATH_BACKUP="$PATH"
export PATH="/nonexistent"
DATABASE_URL="postgresql+asyncpg://x:x@localhost/x" bash setup-tenant.sh 2>&1 | grep -q "Docker not found" && echo "docker-missing guard OK"
export PATH="$PATH_BACKUP"
```

Expected:
```
docker-missing guard OK
```

- [ ] **Step 3: Commit**

```bash
git add setup-tenant.sh
git commit -m "feat(setup-tenant): step 2 — container readiness with health wait"
```

---

### Task 4: Step 3 — Migrations

**Files:**
- Modify: `setup-tenant.sh` (append)

- [ ] **Step 1: Append the migrations block**

Add this to the end of `setup-tenant.sh`:

```bash

# ── Step 3: Migrations ────────────────────────────────────────────────────────
section "Step 3/4: Database migrations"

info "Running Alembic migrations..."
if ! docker compose exec -T api python -m finacialsim_saas.cli.main db migrate 2>&1; then
    die "Migration failed. Check the output above."
fi
ok "Database is up to date"
```

- [ ] **Step 2: Verify the migration command path is correct**

With containers running:
```bash
docker compose exec -T api python -m finacialsim_saas.cli.main db migrate
```

Expected output (any of):
```
Database migrated to head.
```
or Alembic "Target database is not up to date" / "Running upgrade ..." lines.

- [ ] **Step 3: Commit**

```bash
git add setup-tenant.sh
git commit -m "feat(setup-tenant): step 3 — db migrate via CLI"
```

---

### Task 5: Step 4 — Tenant prompts and creation with retry

**Files:**
- Modify: `setup-tenant.sh` (append)

- [ ] **Step 1: Append the tenant creation block**

Add this to the end of `setup-tenant.sh`:

```bash

# ── Step 4: Tenant creation ───────────────────────────────────────────────────
section "Step 4/4: Create first tenant"

_slugify() {
    echo "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed 's/[^a-z0-9]/-/g' \
        | sed 's/--*/-/g' \
        | sed 's/^-//;s/-$//'
}

# Tenant name
if [[ -n "$OPT_NAME" ]]; then
    TENANT_NAME="$OPT_NAME"
else
    read -rp "Tenant name (e.g. Acme Financiadora): " TENANT_NAME
fi
[[ -z "$TENANT_NAME" ]] && die "Tenant name cannot be empty."

# Slug (auto-suggested from name)
_suggested_slug=$(_slugify "$TENANT_NAME")
if [[ -n "$OPT_SLUG" ]]; then
    TENANT_SLUG="$OPT_SLUG"
else
    read -rp "Tenant slug [$_suggested_slug]: " TENANT_SLUG
    TENANT_SLUG="${TENANT_SLUG:-$_suggested_slug}"
fi
[[ -z "$TENANT_SLUG" ]] && die "Tenant slug cannot be empty."

# Admin email
if [[ -n "$OPT_EMAIL" ]]; then
    ADMIN_EMAIL="$OPT_EMAIL"
else
    read -rp "Admin email: " ADMIN_EMAIL
fi
[[ "$ADMIN_EMAIL" =~ ^[^@]+@[^@]+\.[^@]+$ ]] || die "Invalid email address: $ADMIN_EMAIL"

# Admin password — always prompted, never from flags
while true; do
    read -rsp "Admin password (min 8 chars): " ADMIN_PASSWORD
    echo
    if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
        warn "Password must be at least 8 characters."
        continue
    fi
    read -rsp "Confirm password: " ADMIN_PASSWORD2
    echo
    if [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD2" ]]; then
        break
    fi
    warn "Passwords do not match. Try again."
done

# Create tenant — retry up to 3 times on slug collision
_attempt=0
while true; do
    _attempt=$((_attempt + 1))
    if [[ $_attempt -gt 3 ]]; then
        die "Too many failed attempts.\n\n  Run manually:\n    docker compose exec api python -m finacialsim_saas.cli.main tenant create \\\n      --name \"$TENANT_NAME\" --slug <slug> --admin-email \"$ADMIN_EMAIL\""
    fi

    _output=$(docker compose exec -T api python -m finacialsim_saas.cli.main tenant create \
        --name "$TENANT_NAME" \
        --slug "$TENANT_SLUG" \
        --admin-email "$ADMIN_EMAIL" \
        --admin-password "$ADMIN_PASSWORD" 2>&1) && _exit=0 || _exit=$?

    if [[ $_exit -eq 0 ]]; then
        break
    elif echo "$_output" | grep -qi "already exists"; then
        warn "Slug '$TENANT_SLUG' is already taken."
        read -rp "Choose a different slug: " TENANT_SLUG
        [[ -z "$TENANT_SLUG" ]] && die "Slug cannot be empty."
    else
        echo "$_output" >&2
        die "Tenant creation failed. See output above."
    fi
done
```

- [ ] **Step 2: Verify slugify helper**

```bash
bash -c '
source <(grep -A10 "_slugify()" setup-tenant.sh | head -8)
_slugify "Acme Financiadora"
_slugify "  Hello  World!! "
_slugify "UPPER CASE"
'
```

Expected:
```
acme-financiadora
hello-world
upper-case
```

- [ ] **Step 3: Commit**

```bash
git add setup-tenant.sh
git commit -m "feat(setup-tenant): step 4 — tenant prompts, password confirm, slug retry"
```

---

### Task 6: Success summary box

**Files:**
- Modify: `setup-tenant.sh` (append)

- [ ] **Step 1: Append the success summary**

Add this to the end of `setup-tenant.sh`:

```bash

# ── Success ────────────────────────────────────────────────────────────────────
FRONTEND_URL="${FRONTEND_BASE_URL:-http://localhost}"

echo -e "\n${GREEN}${BOLD}"
printf "╔══════════════════════════════════════════════════════╗\n"
printf "║  Tenant created successfully!                        ║\n"
printf "║                                                      ║\n"
printf "║  Name:   %-44s║\n" "$TENANT_NAME "
printf "║  Slug:   %-44s║\n" "$TENANT_SLUG "
printf "║  Admin:  %-44s║\n" "$ADMIN_EMAIL "
printf "║  URL:    %-44s║\n" "$FRONTEND_URL "
printf "╚══════════════════════════════════════════════════════╝\n"
echo -e "${RESET}"
```

- [ ] **Step 2: Verify the box renders without broken alignment**

```bash
bash -c '
GREEN="\033[0;32m"; BOLD="\033[1m"; RESET="\033[0m"
TENANT_NAME="Acme Financiadora"
TENANT_SLUG="acme-financiadora"
ADMIN_EMAIL="admin@acme.com"
FRONTEND_URL="http://localhost"
echo -e "\n${GREEN}${BOLD}"
printf "╔══════════════════════════════════════════════════════╗\n"
printf "║  Tenant created successfully!                        ║\n"
printf "║                                                      ║\n"
printf "║  Name:   %-44s║\n" "$TENANT_NAME "
printf "║  Slug:   %-44s║\n" "$TENANT_SLUG "
printf "║  Admin:  %-44s║\n" "$ADMIN_EMAIL "
printf "║  URL:    %-44s║\n" "$FRONTEND_URL "
printf "╚══════════════════════════════════════════════════════╝\n"
echo -e "${RESET}"
'
```

Expected: a clean aligned box with no broken columns. All lines inside the box should be the same width.

- [ ] **Step 3: Verify final script syntax**

```bash
bash -n setup-tenant.sh && echo "syntax OK"
```

Expected:
```
syntax OK
```

- [ ] **Step 4: Commit**

```bash
git add setup-tenant.sh
git commit -m "feat(setup-tenant): success summary box"
```

---

### Task 7: End-to-end smoke test

**Files:**
- No changes — verification only

- [ ] **Step 1: Verify Docker containers are running**

```bash
docker compose ps
```

Expected: `api`, `db`, `redis` listed with status `Up` / `healthy`.

- [ ] **Step 2: Run the full script non-interactively**

```bash
./setup-tenant.sh \
  --name "Test Tenant" \
  --slug "test-tenant-$(date +%s)" \
  --admin-email "admin@test.local"
```

When prompted for password: enter any password ≥ 8 chars, confirm.

Expected:
- Steps 1–4 all print `✓` or proceed without errors.
- Success box appears with correct Name / Slug / Admin / URL.

- [ ] **Step 3: Verify tenant exists in the database**

```bash
docker compose exec -T api python -m finacialsim_saas.cli.main tenant create \
  --name "Test Tenant" \
  --slug "test-tenant-duplicate" \
  --admin-email "admin2@test.local" \
  --admin-password "password123" 2>&1 || true
# Run the script again with the same slug used above and verify "already taken" prompt appears
```

- [ ] **Step 4: Verify the slug-retry loop**

Run the script again using the same slug from Step 2. The script should warn "Slug '...' is already taken" and prompt for a new one. Enter a new slug — tenant should be created successfully.

- [ ] **Step 5: Verify bad password confirmation is caught**

Run `./setup-tenant.sh` interactively. At the password prompt, enter a mismatched confirmation. Verify the "Passwords do not match" warning appears and it re-prompts.

- [ ] **Step 6: Commit final state**

```bash
git add setup-tenant.sh
git commit -m "feat: add setup-tenant.sh — guided first-tenant setup wizard"
```
