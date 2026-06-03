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
