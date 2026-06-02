#!/usr/bin/env bash
# dev.sh — FinacialSim SaaS local dev runner
#
# Usage:
#   ./dev.sh              — interactive menu
#   ./dev.sh start|stop|restart|status|logs

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_DIR="$ROOT/.dev"
LOGS="$DEV_DIR/logs"
PIDS="$DEV_DIR/pids"
NODE_MIN=20

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

info()    { echo -e "${BLUE}▶${RESET} $*"; }
ok()      { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
die()     { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}$*${RESET}"; }

# ── Setup ─────────────────────────────────────────────────────────────────────
_mkdirs() { mkdir -p "$LOGS" "$PIDS"; }

_pid_file() { echo "$PIDS/$1.pid"; }
_log_file() { echo "$LOGS/$1.log"; }

# ── Dependency checks ─────────────────────────────────────────────────────────
_check_uv() {
    if command -v uv &>/dev/null; then
        ok "uv $(uv --version | awk '{print $2}') found"
        return
    fi
    info "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv &>/dev/null || die "uv install failed. See https://docs.astral.sh/uv/"
    ok "uv installed"
}

_check_node() {
    # Load nvm if available
    [ -f "$HOME/.nvm/nvm.sh" ] && source "$HOME/.nvm/nvm.sh" --no-use 2>/dev/null || true

    local ver=0
    command -v node &>/dev/null && ver=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)

    if [ "$ver" -ge "$NODE_MIN" ] 2>/dev/null; then
        ok "Node $(node --version) found"
        return
    fi

    [ "$ver" -gt 0 ] && warn "Node v${ver} found but ${NODE_MIN}+ required" || warn "Node not found"

    if command -v nvm &>/dev/null; then
        info "Installing Node ${NODE_MIN} via nvm..."
        nvm install "$NODE_MIN" && nvm use "$NODE_MIN"
        ok "Node $(node --version) ready"
    else
        die "Node ${NODE_MIN}+ required. Install nvm: https://github.com/nvm-sh/nvm#install--update-script"
    fi
}

_check_python_deps() {
    local marker="$ROOT/.venv/.dev-synced"
    local needs_sync=false

    [ ! -d "$ROOT/.venv" ] && needs_sync=true
    [ "$ROOT/backend/pyproject.toml" -nt "$marker" ] 2>/dev/null && needs_sync=true
    [ "$ROOT/pyproject.toml" -nt "$marker" ] 2>/dev/null && needs_sync=true

    if $needs_sync; then
        info "Syncing Python dependencies..."
        (cd "$ROOT" && uv sync --extra dev)
        touch "$marker"
        ok "Python deps ready"
    else
        ok "Python deps up to date"
    fi
}

_check_node_deps() {
    local nm="$ROOT/frontend/node_modules"
    if [ ! -d "$nm" ] || [ "$ROOT/frontend/package.json" -nt "$nm" ]; then
        info "Installing frontend dependencies..."
        (cd "$ROOT/frontend" && npm install --silent)
        ok "Frontend deps ready"
    else
        ok "Frontend deps up to date"
    fi
}

_check_mailpit() {
    # Already running?
    if _is_running mailpit; then
        ok "Mailpit already running → http://localhost:8025"
        return
    fi

    # Try Docker
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        docker rm -f finacialsim-mailpit &>/dev/null || true
        docker run -d --name finacialsim-mailpit \
            -p 1025:1025 -p 8025:8025 \
            axllent/mailpit &>/dev/null
        echo "docker:finacialsim-mailpit" > "$(_pid_file mailpit)"
        ok "Mailpit started via Docker → http://localhost:8025"
        return
    fi

    # Try existing binary
    if command -v mailpit &>/dev/null; then
        _start_mailpit_binary && return
    fi

    # Download binary
    info "Mailpit not found — downloading binary..."
    local arch bin_dir="$HOME/.local/bin"
    mkdir -p "$bin_dir"
    arch=$(uname -m); [ "$arch" = "x86_64" ] && arch="amd64" || arch="arm64"
    local url="https://github.com/axllent/mailpit/releases/latest/download/mailpit-linux-${arch}.tar.gz"
    if curl -sSfL "$url" | tar -xz -C "$bin_dir" mailpit 2>/dev/null; then
        chmod +x "$bin_dir/mailpit"
        export PATH="$bin_dir:$PATH"
        _start_mailpit_binary && return
    fi

    warn "Could not install Mailpit — email won't be caught locally."
    warn "Install Docker or set up a local SMTP server manually."
}

_start_mailpit_binary() {
    mailpit \
        --smtp 0.0.0.0:1025 \
        --listen 0.0.0.0:8025 \
        >> "$(_log_file mailpit)" 2>&1 &
    echo $! > "$(_pid_file mailpit)"
    ok "Mailpit started (binary) → http://localhost:8025"
}

_check_env() {
    if [ ! -f "$ROOT/.env" ]; then
        warn ".env not found — creating from .env.example"
        cp "$ROOT/.env.example" "$ROOT/.env"
        echo
        warn "Please review ${ROOT}/.env — especially DATABASE_URL"
        echo -e "${DIM}  Press Enter when ready, or Ctrl+C to cancel${RESET}"
        read -r
    fi
}

check_deps() {
    section "Checking dependencies"
    _check_uv
    _check_node
    _check_python_deps
    _check_node_deps
}

# ── Process management ────────────────────────────────────────────────────────
_is_running() {
    local pidfile; pidfile="$(_pid_file "$1")"
    [ -f "$pidfile" ] || return 1
    local pid; pid=$(cat "$pidfile")

    # Docker container
    if [[ "$pid" == docker:* ]]; then
        docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${pid#docker:}$"
        return $?
    fi

    kill -0 "$pid" 2>/dev/null
}

_stop_one() {
    local name="$1" pidfile
    pidfile="$(_pid_file "$name")"
    [ -f "$pidfile" ] || return 0
    local pid; pid=$(cat "$pidfile")

    if [[ "$pid" == docker:* ]]; then
        local cname="${pid#docker:}"
        docker stop "$cname" &>/dev/null || true
        docker rm   "$cname" &>/dev/null || true
    else
        # Kill process group so child processes (uvicorn reloader, etc.) also die
        local pgid
        pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ') || true
        if [ -n "$pgid" ] && [ "$pgid" != "0" ]; then
            kill -- -"$pgid" 2>/dev/null || true
        else
            kill "$pid" 2>/dev/null || true
        fi
        # Brief wait for clean shutdown
        local i=0
        while kill -0 "$pid" 2>/dev/null && [ $i -lt 8 ]; do
            sleep 0.25; ((i++))
        done
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
}

_any_running() {
    _is_running backend || _is_running worker || _is_running frontend
}

# ── Start / Stop ──────────────────────────────────────────────────────────────
start_app() {
    check_deps
    _check_env
    _mkdirs

    section "Starting services"
    _check_mailpit

    # Backend
    if _is_running backend; then
        warn "Backend already running (pid $(cat "$(_pid_file backend)"))"
    else
        (cd "$ROOT/backend" && exec uv run uvicorn finacialsim_saas.main:app \
            --host 127.0.0.1 --port 8000 --reload) \
            >> "$(_log_file backend)" 2>&1 &
        echo $! > "$(_pid_file backend)"
        ok "Backend  → http://localhost:8000  (log: .dev/logs/backend.log)"
    fi

    # Worker
    if _is_running worker; then
        warn "Worker already running (pid $(cat "$(_pid_file worker)"))"
    else
        (cd "$ROOT/backend" && exec uv run arq \
            finacialsim_saas.workers.worker.WorkerSettings) \
            >> "$(_log_file worker)" 2>&1 &
        echo $! > "$(_pid_file worker)"
        ok "Worker   → ARQ cron active    (log: .dev/logs/worker.log)"
    fi

    # Frontend
    if _is_running frontend; then
        warn "Frontend already running (pid $(cat "$(_pid_file frontend)"))"
    else
        (cd "$ROOT/frontend" && exec npm run dev -- --host 127.0.0.1) \
            >> "$(_log_file frontend)" 2>&1 &
        echo $! > "$(_pid_file frontend)"
        ok "Frontend → http://localhost:5173  (log: .dev/logs/frontend.log)"
    fi

    echo
    echo -e "  ${DIM}Logs: tail -f .dev/logs/*.log${RESET}"
}

stop_app() {
    section "Stopping services"
    local stopped=0
    for name in backend worker frontend mailpit; do
        if _is_running "$name"; then
            _stop_one "$name"
            ok "Stopped $name"
            ((stopped++))
        fi
    done
    [ $stopped -eq 0 ] && info "No services were running"
}

show_status() {
    section "Service status"
    local running=0
    for name in backend worker frontend mailpit; do
        if _is_running "$name"; then
            echo -e "  ${GREEN}●${RESET} $name"
            ((running++))
        else
            echo -e "  ${RED}○${RESET} $name"
        fi
    done
    echo
    if [ $running -gt 0 ]; then
        echo -e "  ${CYAN}http://localhost:8000/healthz${RESET}  backend"
        echo -e "  ${CYAN}http://localhost:5173${RESET}           frontend"
        echo -e "  ${CYAN}http://localhost:8025${RESET}           mailpit"
    fi
}

view_logs() {
    local files=()
    for name in backend worker frontend mailpit; do
        local f; f="$(_log_file "$name")"
        [ -f "$f" ] && files+=("$f")
    done

    if [ ${#files[@]} -eq 0 ]; then
        warn "No log files yet — start the app first"
        return
    fi

    echo
    local i=1
    local names=()
    for name in backend worker frontend mailpit; do
        [ -f "$(_log_file "$name")" ] || continue
        echo "  $i) $name"
        names+=("$name")
        ((i++))
    done
    echo "  $i) All (combined)"
    echo
    read -rp "  Which log? [${i}]: " choice
    choice="${choice:-$i}"

    if [ "$choice" -eq "$i" ] 2>/dev/null; then
        tail -f "${files[@]}"
    elif [ "$choice" -ge 1 ] && [ "$choice" -lt "$i" ] 2>/dev/null; then
        local idx=$(( choice - 1 ))
        tail -f "$(_log_file "${names[$idx]}")"
    else
        warn "Invalid choice"
    fi
}

# ── Menu ──────────────────────────────────────────────────────────────────────
_menu() {
    _mkdirs

    echo -e "${BOLD}${CYAN}"
    echo "  ┌─────────────────────────────────┐"
    echo "  │     FinacialSim SaaS — Dev      │"
    echo "  └─────────────────────────────────┘"
    echo -e "${RESET}"

    show_status

    if _any_running; then
        echo "  1) Restart"
        echo "  2) Stop"
        echo "  3) View logs"
        echo "  4) Exit"
        echo
        read -rp "  Choice [1]: " choice
        case "${choice:-1}" in
            1) stop_app; start_app ;;
            2) stop_app ;;
            3) view_logs ;;
            4|q) exit 0 ;;
            *) warn "Invalid choice" ;;
        esac
    else
        echo "  1) Start"
        echo "  2) Exit"
        echo
        read -rp "  Choice [1]: " choice
        case "${choice:-1}" in
            1) start_app ;;
            2|q) exit 0 ;;
            *) warn "Invalid choice" ;;
        esac
    fi
}

# ── Entry point ───────────────────────────────────────────────────────────────
case "${1:-}" in
    start)   start_app ;;
    stop)    _mkdirs; stop_app ;;
    restart) _mkdirs; stop_app; start_app ;;
    status)  _mkdirs; show_status ;;
    logs)    _mkdirs; view_logs ;;
    *)       _menu ;;
esac
