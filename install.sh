#!/usr/bin/env bash
# =============================================================================
#  dawos-agent installer v2.0
#
#  Interactive, modern installer for the accel-ppp BNG management daemon.
#  Supports fresh install, upgrade, and non-interactive (--yes) modes.
#
#  Usage:
#    sudo bash install.sh              # interactive install
#    sudo bash install.sh --yes        # non-interactive (all defaults)
#    sudo bash install.sh --uninstall  # remove dawos-agent
#
#  Requirements: Debian 11+ / Ubuntu 22.04+, Python 3.10+, root/sudo
# =============================================================================
set -euo pipefail

# ── version ──────────────────────────────────────────────────────────────────
INSTALLER_VERSION="2.0.0"
AGENT_VERSION="0.1.0"

# ── defaults ─────────────────────────────────────────────────────────────────
APP_NAME="dawos-agent"
APP_USER="dawos"
APP_GROUP="dawos"
INSTALL_DIR="/opt/dawos-agent"
VENV_DIR="${INSTALL_DIR}/venv"
CONFIG_DIR="/etc/dawos-agent"
ENV_FILE="${CONFIG_DIR}/agent.env"
SYSTEMD_UNIT="/etc/systemd/system/${APP_NAME}.service"
SUDOERS_FILE="/etc/sudoers.d/${APP_NAME}"

DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT=8470
DEFAULT_LOG_LEVEL="info"
DEFAULT_ACCEL_CONFIG="/etc/accel-ppp.conf"
DEFAULT_ACCEL_CMD="/usr/bin/accel-cmd"
DEFAULT_ACCEL_SERVICE="accel-ppp"

# ── flags ────────────────────────────────────────────────────────────────────
AUTO_YES=false
DO_UNINSTALL=false
UPGRADE_MODE=false

for arg in "$@"; do
    case "$arg" in
        --yes|-y)       AUTO_YES=true ;;
        --uninstall|-u) DO_UNINSTALL=true ;;
        --help|-h)
            echo "Usage: sudo bash install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --yes, -y        Non-interactive mode (accept all defaults)"
            echo "  --uninstall, -u  Remove dawos-agent from this system"
            echo "  --help, -h       Show this help message"
            exit 0
            ;;
    esac
done

# ── color support ────────────────────────────────────────────────────────────
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ $(tput colors 2>/dev/null || echo 0) -ge 8 ]]; then
    BOLD=$(tput bold)
    DIM=$(tput dim)
    RESET=$(tput sgr0)
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
    WHITE=$(tput setaf 7)
else
    BOLD="" DIM="" RESET=""
    RED="" GREEN="" YELLOW="" BLUE="" MAGENTA="" CYAN="" WHITE=""
fi

# ── output helpers ───────────────────────────────────────────────────────────
_line()    { printf '%*s\n' "${COLUMNS:-72}" '' | tr ' ' '─'; }
_blank()   { echo ""; }
_header()  { _blank; echo "  ${BOLD}${CYAN}[$1]${RESET} ${BOLD}$2${RESET}"; _blank; }
_step()    { echo "    ${CYAN}→${RESET} $*"; }
_ok()      { echo "    ${GREEN}✓${RESET} $*"; }
_warn()    { echo "    ${YELLOW}⚠${RESET} $*"; }
_fail()    { echo "    ${RED}✗${RESET} $*" >&2; }
_fatal()   { _fail "$@"; exit 1; }
_info()    { echo "    ${DIM}$*${RESET}"; }
_kv()      { printf "    ${WHITE}%-20s${RESET} %s\n" "$1" "$2"; }

# ── spinner ──────────────────────────────────────────────────────────────────
_spin_pid=""
_spinner() {
    local msg="$1"
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    local i=0
    while true; do
        printf "\r    ${CYAN}%s${RESET} %s " "${frames[$i]}" "$msg"
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.08
    done
}

_spin_start() {
    _spinner "$1" &
    _spin_pid=$!
    disown "$_spin_pid" 2>/dev/null
}

_spin_stop() {
    if [[ -n "$_spin_pid" ]] && kill -0 "$_spin_pid" 2>/dev/null; then
        kill "$_spin_pid" 2>/dev/null
        wait "$_spin_pid" 2>/dev/null || true
        printf "\r%-${COLUMNS:-72}s\r" " "
    fi
    _spin_pid=""
}

# ── prompt helper ────────────────────────────────────────────────────────────
_ask() {
    local var_name="$1" prompt="$2" default="$3"
    if $AUTO_YES; then
        eval "$var_name=\"$default\""
        return
    fi
    local input
    read -rp "    ${MAGENTA}?${RESET} ${prompt} ${DIM}[${default}]${RESET}: " input
    eval "$var_name=\"${input:-$default}\""
}

_confirm() {
    local prompt="$1" default="${2:-y}"
    if $AUTO_YES; then
        return 0
    fi
    local yn
    if [[ "$default" == "y" ]]; then
        read -rp "    ${MAGENTA}?${RESET} ${prompt} ${DIM}[Y/n]${RESET}: " yn
        [[ "${yn,,}" != "n" ]]
    else
        read -rp "    ${MAGENTA}?${RESET} ${prompt} ${DIM}[y/N]${RESET}: " yn
        [[ "${yn,,}" == "y" ]]
    fi
}

_choose() {
    local var_name="$1" prompt="$2"
    shift 2
    local options=("$@")
    if $AUTO_YES; then
        eval "$var_name=\"${options[0]}\""
        return
    fi
    echo "    ${MAGENTA}?${RESET} ${prompt}"
    local i=1
    for opt in "${options[@]}"; do
        if [[ $i -eq 1 ]]; then
            echo "      ${BOLD}${GREEN}${i})${RESET} ${opt} ${DIM}(default)${RESET}"
        else
            echo "      ${WHITE}${i})${RESET} ${opt}"
        fi
        ((i++))
    done
    local choice
    read -rp "      ${DIM}Enter choice [1]:${RESET} " choice
    choice=${choice:-1}
    if [[ "$choice" -ge 1 && "$choice" -le ${#options[@]} ]] 2>/dev/null; then
        eval "$var_name=\"${options[$((choice-1))]}\""
    else
        eval "$var_name=\"${options[0]}\""
    fi
}

# ── trap handler ─────────────────────────────────────────────────────────────
_cleanup() {
    _spin_stop
    if [[ "${1:-}" == "INT" ]]; then
        _blank
        _warn "Installation cancelled by user."
        exit 130
    fi
}
trap '_cleanup INT' INT
trap '_spin_stop' EXIT

# =============================================================================
#  BANNER
# =============================================================================
_banner() {
    clear 2>/dev/null || true
    echo ""
    echo "  ${BOLD}${CYAN}"
    echo "    ┌─────────────────────────────────────────────────────────┐"
    echo "    │                                                         │"
    echo "    │     ██████╗  █████╗ ██╗    ██╗ ██████╗ ███████╗        │"
    echo "    │     ██╔══██╗██╔══██╗██║    ██║██╔═══██╗██╔════╝        │"
    echo "    │     ██║  ██║███████║██║ █╗ ██║██║   ██║███████╗        │"
    echo "    │     ██║  ██║██╔══██║██║███╗██║██║   ██║╚════██║        │"
    echo "    │     ██████╔╝██║  ██║╚███╔███╔╝╚██████╔╝███████║        │"
    echo "    │     ╚═════╝ ╚═╝  ╚═╝ ╚══╝╚══╝  ╚═════╝ ╚══════╝        │"
    echo "    │                                                         │"
    echo "    │       ${WHITE}accel-ppp BNG management agent${CYAN}                  │"
    echo "    │       ${DIM}v${AGENT_VERSION} — installer v${INSTALLER_VERSION}${CYAN}${BOLD}                       │"
    echo "    │                                                         │"
    echo "    └─────────────────────────────────────────────────────────┘"
    echo "  ${RESET}"
    echo ""
}

# =============================================================================
#  UNINSTALL
# =============================================================================
_uninstall() {
    _banner
    _header "UNINSTALL" "Remove dawos-agent from this system"

    if [[ $EUID -ne 0 ]]; then
        _fatal "This script must be run as root (use sudo)"
    fi

    if [[ ! -f "$SYSTEMD_UNIT" ]] && [[ ! -d "$INSTALL_DIR" ]]; then
        _warn "dawos-agent does not appear to be installed."
        exit 0
    fi

    echo "    The following will be removed:"
    [[ -f "$SYSTEMD_UNIT" ]] && _info "  Service:   $SYSTEMD_UNIT"
    [[ -d "$INSTALL_DIR" ]]  && _info "  Install:   $INSTALL_DIR"
    [[ -f "$SUDOERS_FILE" ]] && _info "  Sudoers:   $SUDOERS_FILE"
    _blank

    local keep_config=true
    if _confirm "Keep configuration in ${CONFIG_DIR}?" "y"; then
        keep_config=true
    else
        keep_config=false
    fi
    _blank

    if ! _confirm "Proceed with uninstall?" "n"; then
        _warn "Aborted."
        exit 0
    fi
    _blank

    # Stop & disable service
    if systemctl is-active "$APP_NAME" &>/dev/null; then
        _step "Stopping ${APP_NAME} service..."
        systemctl stop "$APP_NAME"
        _ok "Service stopped"
    fi

    if systemctl is-enabled "$APP_NAME" &>/dev/null; then
        systemctl disable "$APP_NAME" 2>/dev/null || true
    fi

    # Remove systemd unit
    if [[ -f "$SYSTEMD_UNIT" ]]; then
        rm -f "$SYSTEMD_UNIT"
        systemctl daemon-reload
        _ok "Systemd unit removed"
    fi

    # Remove sudoers
    if [[ -f "$SUDOERS_FILE" ]]; then
        rm -f "$SUDOERS_FILE"
        _ok "Sudoers file removed"
    fi

    # Remove install directory
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        _ok "Installation directory removed"
    fi

    # Optionally remove config
    if ! $keep_config && [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        _ok "Configuration removed"
    elif $keep_config; then
        _info "Configuration preserved at ${CONFIG_DIR}"
    fi

    # Remove system user (optional)
    if id "$APP_USER" &>/dev/null; then
        if _confirm "Remove system user '${APP_USER}'?" "n"; then
            userdel "$APP_USER" 2>/dev/null || true
            _ok "User '${APP_USER}' removed"
        else
            _info "User '${APP_USER}' preserved"
        fi
    fi

    _blank
    echo "  ${GREEN}${BOLD}dawos-agent has been uninstalled.${RESET}"
    _blank
    exit 0
}

# =============================================================================
#  PHASE 1 — PREFLIGHT CHECKS
# =============================================================================
_preflight() {
    _header "1/6" "System Requirements Check"
    local issues=0

    # Root check
    if [[ $EUID -ne 0 ]]; then
        _fatal "This script must be run as root (use sudo)"
    fi
    _ok "Running as root"

    # OS detection
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        if [[ "${ID:-}" =~ ^(debian|ubuntu)$ ]]; then
            _ok "Operating system: ${PRETTY_NAME:-$ID}"
        else
            _warn "Unsupported OS: ${PRETTY_NAME:-$ID} — proceeding anyway"
        fi
    else
        _warn "Cannot detect OS — /etc/os-release not found"
    fi

    # Architecture
    local arch
    arch=$(uname -m)
    _ok "Architecture: ${arch}"

    # Python version
    if command -v python3 &>/dev/null; then
        local pyver
        pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
        local pymajor pyminor
        pymajor=$(echo "$pyver" | cut -d. -f1)
        pyminor=$(echo "$pyver" | cut -d. -f2)
        if [[ "$pymajor" -ge 3 ]] && [[ "$pyminor" -ge 10 ]]; then
            _ok "Python: ${pyver} ($(command -v python3))"
        else
            _fail "Python ${pyver} found — requires 3.10+"
            ((issues++))
        fi
    else
        _fail "Python 3 not found"
        ((issues++))
    fi

    # python3-venv
    if python3 -m venv --help &>/dev/null 2>&1; then
        _ok "Python venv module available"
    else
        _warn "python3-venv not found — will attempt to install"
    fi

    # Disk space (require 200MB)
    local avail_kb
    avail_kb=$(df /opt --output=avail 2>/dev/null | tail -1 | tr -d ' ' || echo "0")
    if [[ "$avail_kb" -gt 204800 ]]; then
        _ok "Disk space: $(( avail_kb / 1024 ))MB available in /opt"
    else
        _warn "Low disk space: $(( avail_kb / 1024 ))MB available (200MB recommended)"
    fi

    # accel-ppp check (optional)
    if command -v accel-cmd &>/dev/null; then
        _ok "accel-ppp: detected ($(command -v accel-cmd))"
    else
        _warn "accel-ppp not found — agent can still install (manage it later)"
    fi

    # Existing installation check
    if [[ -d "$INSTALL_DIR" ]] && [[ -f "$ENV_FILE" ]]; then
        UPGRADE_MODE=true
        _warn "Existing installation detected — running in upgrade mode"
        _info "Config will be preserved: ${ENV_FILE}"
    fi

    # Network tools
    for tool in nft ip ss systemctl; do
        if command -v "$tool" &>/dev/null; then
            _ok "${tool}: available"
        else
            _warn "${tool}: not found — some features may not work"
        fi
    done

    if [[ $issues -gt 0 ]]; then
        _blank
        _fatal "Resolve the ${issues} issue(s) above before continuing."
    fi
}

# =============================================================================
#  PHASE 2 — CONFIGURATION WIZARD
# =============================================================================
_saved_api_key=""
_saved_port=""
_saved_host=""
_saved_node=""
_saved_log_level=""
_saved_accel_config=""
_saved_accel_cmd=""
_saved_accel_service=""

_configure() {
    _header "2/6" "Configuration"

    if $UPGRADE_MODE; then
        _ok "Upgrade mode — preserving existing configuration"
        _info "Edit manually: sudo nano ${ENV_FILE}"
        # Load existing values for summary
        if [[ -f "$ENV_FILE" ]]; then
            _saved_api_key=$(grep -E '^DAWOS_API_KEY=' "$ENV_FILE" | cut -d= -f2- || echo "")
            _saved_port=$(grep -E '^DAWOS_PORT=' "$ENV_FILE" | cut -d= -f2- || echo "$DEFAULT_PORT")
            _saved_host=$(grep -E '^DAWOS_HOST=' "$ENV_FILE" | cut -d= -f2- || echo "$DEFAULT_HOST")
            _saved_node=$(grep -E '^DAWOS_NODE_NAME=' "$ENV_FILE" | cut -d= -f2- || echo "$(hostname)")
            _saved_log_level=$(grep -E '^DAWOS_LOG_LEVEL=' "$ENV_FILE" | cut -d= -f2- || echo "$DEFAULT_LOG_LEVEL")
        fi
        return
    fi

    echo "    ${DIM}Configure your dawos-agent installation.${RESET}"
    echo "    ${DIM}Press Enter to accept the default value.${RESET}"
    _blank

    # ── API key ──
    _choose _api_key_mode "How would you like to set the API key?" \
        "Generate a secure random key" \
        "Enter a custom key"

    if [[ "$_api_key_mode" == "Generate a secure random key" ]]; then
        _saved_api_key=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -hex 24)
        _ok "API key generated"
    else
        _ask _saved_api_key "Enter your API key" "my-secret-api-key"
    fi
    _blank

    # ── Network ──
    _ask _saved_host "Listen address" "$DEFAULT_HOST"
    _ask _saved_port "Listen port" "$DEFAULT_PORT"

    # Port conflict check
    if ss -tlnp 2>/dev/null | grep -q ":${_saved_port} " 2>/dev/null; then
        _warn "Port ${_saved_port} is already in use!"
        if ! _confirm "Continue anyway?" "n"; then
            _ask _saved_port "Choose a different port" "8471"
        fi
    fi
    _blank

    # ── Identity ──
    _ask _saved_node "Node name (shown in health checks)" "$(hostname)"
    _blank

    # ── Logging ──
    _choose _saved_log_level "Log level" "info" "debug" "warning" "error"
    _blank

    # ── accel-ppp paths ──
    _ask _saved_accel_config "accel-ppp config path" "$DEFAULT_ACCEL_CONFIG"
    _ask _saved_accel_cmd "accel-cmd binary path" "$DEFAULT_ACCEL_CMD"
    _ask _saved_accel_service "accel-ppp systemd service name" "$DEFAULT_ACCEL_SERVICE"
    _blank

    # ── Confirmation ──
    echo "    ${BOLD}Configuration summary:${RESET}"
    _kv "API Key:" "${_saved_api_key:0:8}...${_saved_api_key: -4} (${#_saved_api_key} chars)"
    _kv "Listen:" "${_saved_host}:${_saved_port}"
    _kv "Node Name:" "$_saved_node"
    _kv "Log Level:" "$_saved_log_level"
    _kv "accel-ppp Config:" "$_saved_accel_config"
    _blank

    if ! _confirm "Proceed with this configuration?" "y"; then
        _warn "Aborted."
        exit 0
    fi
}

# =============================================================================
#  PHASE 3 — SYSTEM SETUP
# =============================================================================
_setup_system() {
    _header "3/6" "System Setup"

    # ── system dependencies ──
    if ! python3 -m venv --help &>/dev/null 2>&1; then
        _spin_start "Installing python3-venv..."
        apt-get update -qq >/dev/null 2>&1
        apt-get install -y -qq python3-venv >/dev/null 2>&1
        _spin_stop
        _ok "python3-venv installed"
    fi

    # ── system user ──
    if id "$APP_USER" &>/dev/null; then
        _ok "Service user '${APP_USER}' already exists"
    else
        useradd --system --no-create-home --shell /usr/sbin/nologin \
            --home-dir "$INSTALL_DIR" "$APP_USER"
        _ok "Created service user '${APP_USER}'"
    fi

    # Add to systemd-journal for log access
    if getent group systemd-journal &>/dev/null; then
        usermod -aG systemd-journal "$APP_USER" 2>/dev/null || true
        _ok "Added '${APP_USER}' to systemd-journal group"
    fi

    # ── directories ──
    mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"
    chown "${APP_USER}:${APP_GROUP}" "$INSTALL_DIR"
    _ok "Directories created"
}

# =============================================================================
#  PHASE 4 — INSTALL PACKAGE
# =============================================================================
_install_package() {
    _header "4/6" "Installing dawos-agent"

    local script_dir repo_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    repo_dir="$script_dir"

    # Detect if running from repo or scripts/ subdirectory
    if [[ -f "${repo_dir}/pyproject.toml" ]]; then
        : # Good — running from repo root
    elif [[ -f "${repo_dir}/../pyproject.toml" ]]; then
        repo_dir="${repo_dir}/.."
    else
        _fatal "Cannot find pyproject.toml — run install.sh from the dawos-agent repository"
    fi

    # ── virtualenv ──
    if [[ ! -d "$VENV_DIR" ]]; then
        _spin_start "Creating Python virtual environment..."
        python3 -m venv "$VENV_DIR"
        _spin_stop
        _ok "Virtual environment created at ${VENV_DIR}"
    else
        _ok "Virtual environment already exists"
    fi

    # ── upgrade pip ──
    _spin_start "Upgrading pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q 2>/dev/null
    _spin_stop
    _ok "pip upgraded"

    # ── install package ──
    _spin_start "Installing dawos-agent package (this may take a moment)..."
    "$VENV_DIR/bin/pip" install "$repo_dir" -q 2>/dev/null
    _spin_stop

    local installed_version
    installed_version=$("$VENV_DIR/bin/pip" show dawos-agent 2>/dev/null | grep "^Version:" | awk '{print $2}' || echo "unknown")
    _ok "dawos-agent v${installed_version} installed"

    # ── ownership ──
    chown -R "${APP_USER}:${APP_GROUP}" "$INSTALL_DIR"
    _ok "Permissions set"

    # ── configuration file ──
    if $UPGRADE_MODE; then
        _ok "Configuration preserved (upgrade mode)"
    else
        cat > "$ENV_FILE" <<EOF
# ─────────────────────────────────────────────────────────────────────
# dawos-agent configuration
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) by installer v${INSTALLER_VERSION}
# ─────────────────────────────────────────────────────────────────────

# API authentication — share this key with your management platform
DAWOS_API_KEY=${_saved_api_key}

# Network binding
DAWOS_HOST=${_saved_host}
DAWOS_PORT=${_saved_port}

# Node identity (appears in health checks and logs)
DAWOS_NODE_NAME=${_saved_node}

# accel-ppp integration
ACCEL_CMD=${_saved_accel_cmd:-$DEFAULT_ACCEL_CMD}
ACCEL_CLI_PORT=2001
ACCEL_CONFIG_PATH=${_saved_accel_config:-$DEFAULT_ACCEL_CONFIG}
ACCEL_SERVICE_NAME=${_saved_accel_service:-$DEFAULT_ACCEL_SERVICE}

# Logging (debug | info | warning | error)
DAWOS_LOG_LEVEL=${_saved_log_level:-$DEFAULT_LOG_LEVEL}
EOF
        chmod 0640 "$ENV_FILE"
        chown "root:${APP_GROUP}" "$ENV_FILE"
        _ok "Configuration written to ${ENV_FILE}"
    fi
}

# =============================================================================
#  PHASE 5 — SYSTEMD & SECURITY
# =============================================================================
_install_service() {
    _header "5/6" "Service & Security"

    local script_dir repo_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    repo_dir="$script_dir"
    [[ -f "${repo_dir}/../pyproject.toml" ]] && repo_dir="${repo_dir}/.."

    # ── sudoers ──
    local sudoers_src="${repo_dir}/deploy/dawos-agent.sudoers"
    if [[ -f "$sudoers_src" ]]; then
        cp "$sudoers_src" "$SUDOERS_FILE"
        chmod 0440 "$SUDOERS_FILE"
        if visudo -cf "$SUDOERS_FILE" &>/dev/null; then
            _ok "Sudoers installed (least-privilege rules)"
        else
            rm -f "$SUDOERS_FILE"
            _warn "Sudoers syntax check failed — skipped"
        fi
    else
        # Generate inline sudoers
        cat > "$SUDOERS_FILE" <<'SUDOERS'
# dawos-agent — passwordless sudo for BNG management commands
dawos ALL=(ALL) NOPASSWD: /usr/sbin/nft
dawos ALL=(ALL) NOPASSWD: /usr/sbin/ip
dawos ALL=(ALL) NOPASSWD: /usr/sbin/tc
dawos ALL=(ALL) NOPASSWD: /usr/bin/vtysh
dawos ALL=(ALL) NOPASSWD: /usr/sbin/sysctl
dawos ALL=(ALL) NOPASSWD: /usr/bin/tee
SUDOERS
        chmod 0440 "$SUDOERS_FILE"
        _ok "Sudoers installed (inline rules)"
    fi

    # ── systemd unit ──
    local service_src="${repo_dir}/systemd/dawos-agent.service"
    if [[ -f "$service_src" ]]; then
        cp "$service_src" "$SYSTEMD_UNIT"
    else
        cat > "$SYSTEMD_UNIT" <<'SERVICE'
[Unit]
Description=dawos-agent — accel-ppp BNG management daemon
Documentation=https://github.com/Cepat-Kilat-Teknologi/accel-app
After=network-online.target accel-ppp.service
Wants=network-online.target

[Service]
Type=simple
User=dawos
Group=dawos
EnvironmentFile=-/etc/dawos-agent/agent.env
ExecStart=/opt/dawos-agent/venv/bin/dawos-agent
Restart=on-failure
RestartSec=5
StartLimitBurst=3
StartLimitIntervalSec=60

NoNewPrivileges=false
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/etc/accel-ppp.conf /etc/accel-ppp.d /etc/accel-nat-egress.nft /etc/sysctl.d /etc/nftables.conf
PrivateTmp=true

StandardOutput=journal
StandardError=journal
SyslogIdentifier=dawos-agent

[Install]
WantedBy=multi-user.target
SERVICE
    fi

    systemctl daemon-reload
    _ok "Systemd unit installed"

    # ── enable & start ──
    systemctl enable "$APP_NAME" 2>/dev/null || true
    _ok "Service enabled (starts on boot)"

    _step "Starting ${APP_NAME}..."
    if systemctl start "$APP_NAME" 2>/dev/null; then
        sleep 1
        if systemctl is-active "$APP_NAME" &>/dev/null; then
            _ok "Service is running"
        else
            _warn "Service started but may not be active yet"
        fi
    else
        _warn "Service failed to start — check: journalctl -u ${APP_NAME} -n 20"
    fi
}

# =============================================================================
#  PHASE 6 — HEALTH CHECK & SUMMARY
# =============================================================================
_health_check() {
    _header "6/6" "Verification"

    local port
    port=$(grep -E '^DAWOS_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "$DEFAULT_PORT")
    local url="http://localhost:${port}"
    local max_retries=5
    local retry=0
    local healthy=false

    _step "Waiting for dawos-agent to respond..."
    while [[ $retry -lt $max_retries ]]; do
        if curl -sf "${url}/health" >/dev/null 2>&1; then
            healthy=true
            break
        fi
        sleep 1
        ((retry++))
    done

    if $healthy; then
        local health_json
        health_json=$(curl -sf "${url}/health" 2>/dev/null || echo '{}')
        _ok "Health check passed!"
        _blank

        # Parse health response
        local node_name agent_version
        node_name=$(echo "$health_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('node_name','?'))" 2>/dev/null || echo "?")
        agent_version=$(echo "$health_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")

        _kv "Node:" "$node_name"
        _kv "Version:" "$agent_version"
        _kv "Status:" "${GREEN}healthy${RESET}"
    else
        _warn "Health check timed out — service may still be starting"
        _info "Try manually: curl ${url}/health"
    fi
}

_summary() {
    local port api_key host_ip
    port=$(grep -E '^DAWOS_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "$DEFAULT_PORT")
    api_key=$(grep -E '^DAWOS_API_KEY=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "?")
    host_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

    _blank
    echo "  ${BOLD}${GREEN}┌─────────────────────────────────────────────────────────┐${RESET}"
    echo "  ${BOLD}${GREEN}│                                                         │${RESET}"
    echo "  ${BOLD}${GREEN}│          Installation Complete!                         │${RESET}"
    echo "  ${BOLD}${GREEN}│                                                         │${RESET}"
    echo "  ${BOLD}${GREEN}└─────────────────────────────────────────────────────────┘${RESET}"
    _blank

    echo "  ${BOLD}  Access${RESET}"
    _kv "  Agent URL:" "http://${host_ip}:${port}"
    _kv "  API Docs:" "http://${host_ip}:${port}/docs"
    _kv "  Health:" "http://${host_ip}:${port}/health"
    _blank

    echo "  ${BOLD}  Authentication${RESET}"
    _kv "  API Key:" "${api_key}"
    _kv "  Header:" "X-API-Key: <key>"
    _blank

    echo "  ${BOLD}  File Locations${RESET}"
    _kv "  Config:" "$ENV_FILE"
    _kv "  Install:" "$INSTALL_DIR"
    _kv "  Service:" "$SYSTEMD_UNIT"
    _kv "  Logs:" "journalctl -u ${APP_NAME}"
    _blank

    echo "  ${BOLD}  Useful Commands${RESET}"
    _kv "  Status:" "sudo systemctl status ${APP_NAME}"
    _kv "  Restart:" "sudo systemctl restart ${APP_NAME}"
    _kv "  Logs:" "journalctl -u ${APP_NAME} -f"
    _kv "  Edit Config:" "sudo nano ${ENV_FILE}"
    _kv "  Uninstall:" "sudo bash install.sh --uninstall"
    _blank

    echo "  ${BOLD}  Quick Test${RESET}"
    echo "    ${DIM}curl -s -H 'X-API-Key: ${api_key}' http://localhost:${port}/api/v1/health | python3 -m json.tool${RESET}"
    _blank

    echo "  ${YELLOW}${BOLD}  ⚠ Save your API key — you'll need it to register this node!${RESET}"
    _blank
    _line
    _blank
}

# =============================================================================
#  MAIN
# =============================================================================
main() {
    # Handle uninstall
    if $DO_UNINSTALL; then
        _uninstall
    fi

    _banner

    if $AUTO_YES; then
        _info "Running in non-interactive mode (--yes)"
        _blank
    fi

    _preflight
    _configure
    _setup_system
    _install_package
    _install_service
    _health_check
    _summary
}

main "$@"
