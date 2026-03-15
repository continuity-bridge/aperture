#!/usr/bin/env bash
# install-aperture.sh
# One-shot installer for Aperture MCP bridge.
# Installs dependencies, sets up the service, walks user through setup.
#
# Author: Jerry Jackson (Uncle Tallest) & Vector
# Version: v0.3.1
# Requires: Linux, Python 3.10+, systemd (optional but recommended)

set -euo pipefail

APERTURE_DIR="$HOME/.aperture"
SERVICE_NAME="aperture"
REPO_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}!${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
ask()     { echo -e "${CYAN}?${NC} $*"; }
section() { echo -e "\n${BOLD}── $* ──${NC}"; }
die()     { error "$*"; exit 1; }

# ── Welcome ───────────────────────────────────────────────────────────────────

clear
echo -e "${BOLD}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       Aperture MCP Bridge             ║"
echo "  ║       Installer v0.3.1                ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo "  This installer will:"
echo "  1. Check your system has what's needed"
echo "  2. Install Python dependencies"
echo "  3. Ask which folder(s) Claude can access"
echo "  4. Set up Aperture to run automatically"
echo "  5. Give you a URL to paste into claude.ai"
echo ""
echo "  Estimated time: 2-3 minutes"
echo ""
read -rp "  Press Enter to continue (Ctrl+C to cancel)..."

# ── System checks ─────────────────────────────────────────────────────────────

section "Checking system requirements"

# Python 3.10+
if ! command -v python3 &>/dev/null; then
    die "Python 3 not found. Install it with: sudo apt install python3"
fi

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor:02d}")')
if [[ "$PYVER" -lt 310 ]]; then
    die "Python 3.10 or newer required. You have $(python3 --version). Try: sudo apt install python3.12"
fi
info "Python $(python3 --version)"

# pip
if ! python3 -m pip --version &>/dev/null; then
    warn "pip not found -- installing..."
    sudo apt-get install -y python3-pip || die "Could not install pip"
fi
info "pip available"

# ssh (for serveo tunnel)
if ! command -v ssh &>/dev/null; then
    warn "SSH not found -- installing..."
    sudo apt-get install -y openssh-client || die "Could not install ssh"
fi
info "SSH available"

# systemd (optional)
HAS_SYSTEMD=false
if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    HAS_SYSTEMD=true
    info "systemd available (will set up autostart)"
else
    warn "systemd not available -- Aperture will need to be started manually"
fi

# Internet reachable
if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
        serveo.net echo ok &>/dev/null 2>&1; then
    warn "Could not reach serveo.net -- tunnel will be tested later."
    warn "If it fails, check your firewall allows outbound SSH (port 22)."
fi

# ── Install Python dependencies ───────────────────────────────────────────────

section "Installing Python dependencies"

DEPS=(flask flask-cors mcp httpx starlette uvicorn)

for dep in "${DEPS[@]}"; do
    if python3 -c "import ${dep//-/_}" &>/dev/null 2>&1; then
        info "$dep already installed"
    else
        echo -n "  Installing $dep..."
        python3 -m pip install "$dep" --break-system-packages -q \
            && echo -e " ${GREEN}done${NC}" \
            || die "Failed to install $dep"
    fi
done

# ── Copy files to install dir ─────────────────────────────────────────────────

section "Installing Aperture files"

mkdir -p "$APERTURE_DIR"
cp "$REPO_SCRIPT_DIR/aperture.py"            "$APERTURE_DIR/"
cp "$REPO_SCRIPT_DIR/aperture-mcp-server.py" "$APERTURE_DIR/"
cp "$REPO_SCRIPT_DIR/aperture-start.sh"      "$APERTURE_DIR/"
chmod +x "$APERTURE_DIR/aperture-start.sh"

info "Files installed to $APERTURE_DIR"

# ── Configure allowed directories ────────────────────────────────────────────

section "Configure: which folders can Claude access?"

echo ""
echo "  Claude will only be able to read and write files"
echo "  inside the folders you specify here."
echo ""
echo "  You can add multiple folders. Press Enter with"
echo "  an empty line when you're done."
echo ""
echo "  Examples:"
echo "    /home/$(whoami)/Documents/claude-work"
echo "    /home/$(whoami)/Projects"
echo ""

ALLOW_DIRS=()
while true; do
    ask "Enter a folder path (or press Enter to finish):"
    read -r -p "  > " DIR
    if [[ -z "$DIR" ]]; then
        if [[ ${#ALLOW_DIRS[@]} -eq 0 ]]; then
            warn "You must add at least one folder."
            continue
        fi
        break
    fi
    DIR="${DIR/#\~/$HOME}"  # expand ~
    if [[ ! -d "$DIR" ]]; then
        warn "Folder not found: $DIR"
        ask "Create it? [y/N]"
        read -r -p "  > " CREATE
        if [[ "${CREATE,,}" == "y" ]]; then
            mkdir -p "$DIR"
            info "Created: $DIR"
        else
            continue
        fi
    fi
    ALLOW_DIRS+=("$DIR")
    info "Added: $DIR"
done

# ── Choose subdomain ──────────────────────────────────────────────────────────

section "Configure: tunnel subdomain"

DEFAULT_SUBDOMAIN="aperture-$(whoami | tr -cd '[:alnum:]-' | head -c12)-$(hostname -s | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]-' | head -c12)"

echo ""
echo "  Aperture uses a free tunnel service (serveo.net) so"
echo "  claude.ai can reach your computer."
echo ""
echo "  You can claim a custom subdomain -- if it's available,"
echo "  your URL will always be the same."
echo ""
echo "  Default: ${DEFAULT_SUBDOMAIN}.serveo.net"
echo ""
ask "Subdomain (press Enter for default):"
read -r -p "  > " SUBDOMAIN
SUBDOMAIN="${SUBDOMAIN:-$DEFAULT_SUBDOMAIN}"
SUBDOMAIN=$(echo "$SUBDOMAIN" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]-')

info "Will use subdomain: $SUBDOMAIN"

# ── Write config ──────────────────────────────────────────────────────────────

section "Saving configuration"

{
    echo "# Aperture configuration"
    echo "# Generated by install-aperture.sh on $(date)"
    echo ""
    echo "SUBDOMAIN=\"$SUBDOMAIN\""
    echo "ALLOW_DIRS=("
    for dir in "${ALLOW_DIRS[@]}"; do
        echo "  \"$dir\""
    done
    echo ")"
} > "$HOME/.aperture.conf"

info "Config saved to ~/.aperture.conf"

# ── Set up systemd autostart ──────────────────────────────────────────────────

if [[ "$HAS_SYSTEMD" == "true" ]]; then
    section "Setting up autostart (systemd)"

    ALLOW_ARGS=""
    for dir in "${ALLOW_DIRS[@]}"; do
        ALLOW_ARGS="$ALLOW_ARGS --allow $dir"
    done

    mkdir -p "$HOME/.config/systemd/user"

    cat > "$HOME/.config/systemd/user/aperture.service" << EOF
[Unit]
Description=Aperture MCP Bridge for claude.ai
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$APERTURE_DIR/aperture-start.sh --subdomain $SUBDOMAIN $ALLOW_ARGS
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable aperture.service
    info "Autostart enabled (starts on login)"

    ask "Start Aperture now? [Y/n]"
    read -r -p "  > " START_NOW
    if [[ "${START_NOW,,}" != "n" ]]; then
        systemctl --user start aperture.service
        info "Started."
        sleep 3
    fi
else
    section "Manual start"
    echo "  Since systemd isn't available, start Aperture manually with:"
    echo ""
    echo -e "  ${CYAN}$APERTURE_DIR/aperture-start.sh${NC}"
    echo ""
    ask "Start Aperture now? [Y/n]"
    read -r -p "  > " START_NOW
    if [[ "${START_NOW,,}" != "n" ]]; then
        bash "$APERTURE_DIR/aperture-start.sh"
    fi
fi

# ── Show connector URL ────────────────────────────────────────────────────────

section "All done!"

CONNECTOR_URL="https://${SUBDOMAIN}.serveo.net/sse"

echo ""
echo -e "${GREEN}┌─────────────────────────────────────────────────────────┐${NC}"
echo -e "${GREEN}│  Aperture installed successfully                        │${NC}"
echo -e "${GREEN}├─────────────────────────────────────────────────────────┤${NC}"
echo -e "${GREEN}│${NC}                                                         ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Add this URL in claude.ai:                             ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Settings → Connectors → + → Custom MCP Server          ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}                                                         ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  ${CYAN}${CONNECTOR_URL}${NC}"
echo -e "${GREEN}│${NC}                                                         ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}  Commands:                                               ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}    Stop:    aperture-start.sh --stop                     ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}    Status:  aperture-start.sh --status                   ${GREEN}│${NC}"
echo -e "${GREEN}│${NC}    Restart: aperture-start.sh                            ${GREEN}│${NC}"
echo -e "${GREEN}└─────────────────────────────────────────────────────────┘${NC}"
echo ""

# Symlink to PATH if possible
if [[ -d "$HOME/.local/bin" ]]; then
    ln -sf "$APERTURE_DIR/aperture-start.sh" "$HOME/.local/bin/aperture-start.sh" 2>/dev/null || true
    info "aperture-start.sh added to ~/.local/bin"
fi

echo ""
echo "  If the URL above doesn't connect, wait 30 seconds and"
echo "  check status with: aperture-start.sh --status"
echo ""
