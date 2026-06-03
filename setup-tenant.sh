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
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

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
        --name)
            [[ $# -lt 2 || -z "${2:-}" ]] && die "--name requires a value"
            OPT_NAME="$2"; shift 2 ;;
        --slug)
            [[ $# -lt 2 || -z "${2:-}" ]] && die "--slug requires a value"
            OPT_SLUG="$2"; shift 2 ;;
        --admin-email)
            [[ $# -lt 2 || -z "${2:-}" ]] && die "--admin-email requires a value"
            OPT_EMAIL="$2"; shift 2 ;;
        *) die "Unknown option: $1\nUsage: ./setup-tenant.sh [--name NAME] [--slug SLUG] [--admin-email EMAIL]" ;;
    esac
done

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

# ── Step 2: Container readiness ───────────────────────────────────────────────
section "Step 2/4: Container readiness"

if ! command -v docker &>/dev/null; then
    die "Docker not found. Install Docker Engine or Docker Desktop:\n  https://docs.docker.com/get-docker/"
fi

cd "$ROOT"

_api_healthy() {
    docker compose ps api 2>/dev/null | grep -q "(healthy)"
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

# ── Step 3: Migrations ────────────────────────────────────────────────────────
section "Step 3/4: Database migrations"

info "Running Alembic migrations..."
if ! docker compose exec -T api python -m finacialsim_saas.cli.main db migrate 2>&1; then
    die "Migration failed. Check the output above."
fi
ok "Database is up to date"

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

    _output=$(printf '%s\n' "$ADMIN_PASSWORD" | docker compose exec -T api python -m finacialsim_saas.cli.main tenant create \
        --name "$TENANT_NAME" \
        --slug "$TENANT_SLUG" \
        --admin-email "$ADMIN_EMAIL" 2>&1) && _exit=0 || _exit=$?

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
