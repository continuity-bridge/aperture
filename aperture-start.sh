#!/usr/bin/env bash
# aperture-start.sh
# Can also be called as: aperture-start.sh --stop | --status
# Starts the Aperture MCP bridge, SSE server, and Serveo tunnel.
# Usage: ./aperture-start.sh [--allow /path/to/dir] [--subdomain my-aperture]
#
# Author: Jerry Jackson (Uncle Tallest) & Vector
# Version: v0.3.2
# Fixed: Function ordering bug, serveousercontent.com domain support

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$HOME/.aperture.conf"
PID_DIR="$HOME/.aperture-pids"
LOG_DIR="$HOME/.aperture-logs"
BRIDGE_PORT=8765
MCP_PORT=10000
SUBDOMAIN=""
ALLOW_DIRS=()

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${GREEN}[aperture]${NC} $*"; }
warn()    { echo -e "${YELLOW}[aperture]${NC} $*"; }
error()   { echo -e "${RED}[aperture]${NC} $*" >&2; }
section() { echo -e "\n${CYAN}── $* ──${NC}"; }

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Helper functions ──────────────────────────────────────────────────────────

is_running() {
    local pid_file="$PID_DIR/$1.pid"
    [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

stop_process() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 0.5
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    fi
}

# ── do_ arguments ──────────────────────────────────────────────────────────

do_stop() {
    section "Stopping Aperture"
    stop_process "bridge"
    stop_process "mcp"
    stop_process "tunnel"
    rm -f "$HOME/.aperture-token" 2>/dev/null || true
    info "Stopped."
}

do_status() {
    section "Aperture Status"
    for svc in bridge mcp tunnel; do
        if is_running "$svc"; then
            echo -e "  ${GREEN}●${NC} $svc (PID $(cat "$PID_DIR/$svc.pid"))"
        else
            echo -e "  ${RED}○${NC} $svc (not running)"
        fi
    done
    if [[ -f "$HOME/.aperture-url" ]]; then
        echo ""
        echo -e "  Connector URL: ${CYAN}$(cat "$HOME/.aperture-url")${NC}"
    fi
}


# ── Parse arguments ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case $1 in
        --allow)    ALLOW_DIRS+=("$2"); shift 2 ;;
        --subdomain) SUBDOMAIN="$2"; shift 2 ;;
        --stop)     do_stop; exit 0 ;;
        --status)   do_status; exit 0 ;;
        *) error "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Load config if no args provided ──────────────────────────────────────────

if [[ ${#ALLOW_DIRS[@]} -eq 0 && -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
fi

if [[ ${#ALLOW_DIRS[@]} -eq 0 ]]; then
    error "No allowed directories specified."
    echo "  Run: $0 --allow /path/to/your/files"
    echo "  Or create $CONFIG_FILE with:"
    echo '  ALLOW_DIRS=("/home/yourname/Documents")'
    echo '  SUBDOMAIN="my-aperture"'
    exit 1
fi

if [[ -z "$SUBDOMAIN" ]]; then
    SUBDOMAIN="aperture-$(whoami | tr -cd '[:alnum:]-' | head -c12)-$(hostname -s | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]-' | head -c12)"
fi

# ── Stop anything already running ────────────────────────────────────────────

if is_running "bridge" || is_running "mcp" || is_running "tunnel"; then
    warn "Existing processes found -- stopping them first."
    do_stop
fi

# ── Build --allow args ────────────────────────────────────────────────────────

ALLOW_ARGS=()
for dir in "${ALLOW_DIRS[@]}"; do
    ALLOW_ARGS+=(--allow "$dir")
done

# ── Start aperture bridge ─────────────────────────────────────────────────────

section "Starting aperture bridge (port $BRIDGE_PORT)"

python3 "$SCRIPT_DIR/aperture.py" start "${ALLOW_ARGS[@]}" \
    > "$LOG_DIR/bridge.log" 2>&1 &
BRIDGE_PID=$!
echo "$BRIDGE_PID" > "$PID_DIR/bridge.pid"

# Wait for bridge to be ready and grab token
for i in {1..20}; do
    if grep -q "Session token:" "$LOG_DIR/bridge.log" 2>/dev/null; then
        break
    fi
    sleep 0.3
done

TOKEN=$(grep "Session token:" "$LOG_DIR/bridge.log" 2>/dev/null | head -1 | awk '{print $NF}' || true)

if [[ -z "$TOKEN" ]]; then
    error "Bridge failed to start. Check $LOG_DIR/bridge.log"
    cat "$LOG_DIR/bridge.log" >&2
    exit 1
fi

echo "$TOKEN" > "$HOME/.aperture-token"
chmod 600 "$HOME/.aperture-token"
info "Bridge running (PID $BRIDGE_PID, token saved)"

# ── Start MCP SSE server ──────────────────────────────────────────────────────

section "Starting MCP SSE server (port $MCP_PORT)"

python3 "$SCRIPT_DIR/aperture-mcp-server.py" --port "$MCP_PORT" \
    > "$LOG_DIR/mcp.log" 2>&1 &
MCP_PID=$!
echo "$MCP_PID" > "$PID_DIR/mcp.pid"

# Wait for uvicorn ready
for i in {1..20}; do
    if grep -q "Application startup complete" "$LOG_DIR/mcp.log" 2>/dev/null; then
        break
    fi
    sleep 0.3
done

if ! is_running "mcp"; then
    error "MCP server failed to start. Check $LOG_DIR/mcp.log"
    cat "$LOG_DIR/mcp.log" >&2
    exit 1
fi

info "MCP server running (PID $MCP_PID)"

# ── Start Serveo tunnel ───────────────────────────────────────────────────────

section "Starting Serveo tunnel (subdomain: $SUBDOMAIN)"

ssh -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -R "${SUBDOMAIN}:80:localhost:${MCP_PORT}" \
    serveo.net \
    > "$LOG_DIR/tunnel.log" 2>&1 &
TUNNEL_PID=$!
echo "$TUNNEL_PID" > "$PID_DIR/tunnel.pid"

# Wait for tunnel URL
TUNNEL_URL=""
for i in {1..30}; do
    TUNNEL_URL=$(grep -oP 'https://\S+\.serveo(usercontent\.com|\.net)' "$LOG_DIR/tunnel.log" 2>/dev/null | head -1 || true)
    if [[ -n "$TUNNEL_URL" ]]; then
        break
    fi
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
        error "Tunnel process died. Check $LOG_DIR/tunnel.log"
        cat "$LOG_DIR/tunnel.log" >&2
        exit 1
    fi
    sleep 0.5
done

if [[ -z "$TUNNEL_URL" ]]; then
    # Subdomain might be taken -- try with random suffix
    warn "Could not claim subdomain '$SUBDOMAIN' -- trying with random suffix."
    stop_process "tunnel"
    SUBDOMAIN="${SUBDOMAIN}-$(head -c4 /dev/urandom | xxd -p)"
    ssh -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -R "${SUBDOMAIN}:80:localhost:${MCP_PORT}" \
        serveo.net \
        > "$LOG_DIR/tunnel.log" 2>&1 &
    TUNNEL_PID=$!
    echo "$TUNNEL_PID" > "$PID_DIR/tunnel.pid"
    for i in {1..30}; do
        TUNNEL_URL=$(grep -oP 'https://\S+\.serveo(usercontent\.com|\.net)' "$LOG_DIR/tunnel.log" 2>/dev/null | head -1 || true)
        [[ -n "$TUNNEL_URL" ]] && break
        sleep 0.5
    done
fi

if [[ -z "$TUNNEL_URL" ]]; then
    error "Failed to establish Serveo tunnel. Is serveo.net reachable?"
    echo "  Check: ssh -R test:80:localhost:$MCP_PORT serveo.net"
    exit 1
fi

CONNECTOR_URL="${TUNNEL_URL}/sse"
echo "$CONNECTOR_URL" > "$HOME/.aperture-url"
info "Tunnel running (PID $TUNNEL_PID)"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}┌─────────────────────────────────────────────────────┐${NC}"
echo -e "${GREEN}│  Aperture is running                                │${NC}"
echo -e "${GREEN}├─────────────────────────────────────────────────────┤${NC}"
echo -e "${GREEN}│${NC}  Connector URL (paste into claude.ai):              ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  ${CYAN}${CONNECTOR_URL}${NC}"
echo -e "${GREEN}│${NC}                                                     ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Logs: $LOG_DIR/           ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Stop: $0 --stop     ${GREEN}│${NC}"
echo -e "${GREEN}└─────────────────────────────────────────────────────┘${NC}"
echo ""

# Save for re-display
cat > "$HOME/.aperture-status" << EOF
CONNECTOR_URL=$CONNECTOR_URL
SUBDOMAIN=$SUBDOMAIN
STARTED=$(date)
EOF
