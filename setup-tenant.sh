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
