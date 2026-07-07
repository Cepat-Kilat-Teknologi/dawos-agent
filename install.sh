#!/usr/bin/env bash
# =============================================================================
#  dawos-agent installer v2.0
#
#  Interactive installer for dawos-agent PPP router management daemon.
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

# ── source repo ──────────────────────────────────────────────────────────────
REPO_OWNER="Cepat-Kilat-Teknologi"
REPO_NAME="dawos-agent"
REPO_BRANCH="main"
REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"
TARBALL_URL="${REPO_URL}/archive/refs/heads/${REPO_BRANCH}.tar.gz"
SOURCE_DIR=""

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
    echo "    │       ${WHITE}PPP router management agent${CYAN}                     │"
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
#  PREFLIGHT
# =============================================================================
_preflight() {
    _header "CHECK" "System requirements"
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
        _warn "accel-ppp not found — will offer to install from source"
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
#  CONFIGURE
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
    _header "CONFIG" "Configuration"

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
#  SYSTEM SETUP
# =============================================================================
_setup_system() {
    _header "SETUP" "System setup"

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
#  ACCEL-PPP (optional)
# =============================================================================
_install_accel_ppp() {
    _header "ACCEL-PPP" "accel-ppp PPPoE/PPTP/L2TP server"

    # ── already installed? ──
    if command -v accel-pppd &>/dev/null; then
        local ver
        ver=$(accel-pppd --version 2>&1 | head -1 || echo "unknown")
        _ok "accel-ppp already installed (${ver})"
        _ensure_accel_config
        _ensure_accel_service
        return
    fi

    # ── prompt (default yes, auto-yes installs) ──
    if ! _confirm "Install accel-ppp from source? (recommended)" "y"; then
        _warn "Skipping accel-ppp — you can install it manually later"
        _info "dawos-agent will still run but PPP-related endpoints will return errors"
        return
    fi

    _step "Installing build dependencies..."
    _spin_start "apt-get install build deps..."
    apt-get update -qq >/dev/null 2>&1
    apt-get install -y -qq \
        cmake gcc g++ make git \
        libssl-dev libpcre2-dev libpcre3-dev liblua5.1-0-dev \
        "linux-headers-$(uname -r)" \
        >/dev/null 2>&1
    _spin_stop
    _ok "Build dependencies installed"

    # ── clone source ──
    local build_dir="/tmp/accel-ppp-build"
    rm -rf "$build_dir"
    _spin_start "Cloning accel-ppp source..."
    if ! git clone --depth 1 https://github.com/accel-ppp/accel-ppp.git "$build_dir" >/dev/null 2>&1; then
        _spin_stop
        _fail "Failed to clone accel-ppp repository"
        _warn "Skipping accel-ppp installation — check network connectivity"
        return
    fi
    _spin_stop
    _ok "Source cloned"

    # ── build ──
    mkdir -p "${build_dir}/build"
    _spin_start "Building accel-ppp (this may take 2-5 minutes)..."
    if ! (
        cd "${build_dir}/build" && \
        cmake \
            -DBUILD_IPOE_DRIVER=TRUE \
            -DBUILD_VLAN_MON_DRIVER=TRUE \
            -DCMAKE_INSTALL_PREFIX=/usr \
            -DKDIR="/usr/src/linux-headers-$(uname -r)" \
            -DLUA=TRUE \
            -DRADIUS=TRUE \
            .. >/dev/null 2>&1 && \
        make -j"$(nproc)" >/dev/null 2>&1
    ); then
        _spin_stop
        _fail "Build failed — check kernel headers and compiler"
        _warn "Skipping accel-ppp installation"
        rm -rf "$build_dir"
        return
    fi
    _spin_stop
    _ok "Build succeeded"

    # ── install ──
    _spin_start "Installing accel-ppp..."
    if ! (cd "${build_dir}/build" && make install >/dev/null 2>&1); then
        _spin_stop
        _fail "make install failed"
        rm -rf "$build_dir"
        return
    fi
    _spin_stop
    _ok "accel-ppp installed to /usr/sbin/accel-pppd"

    # ── cleanup build dir ──
    rm -rf "$build_dir"

    # ── config ──
    _ensure_accel_config

    # ── systemd service ──
    _ensure_accel_service
}

_ensure_accel_service() {
    if [[ -f /etc/systemd/system/accel-ppp.service ]]; then
        _ok "accel-ppp systemd unit exists"
        return
    fi

    cat > /etc/systemd/system/accel-ppp.service <<'ACCELUNIT'
[Unit]
Description=accel-ppp — high-performance PPPoE/PPTP/L2TP server
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
PIDFile=/var/run/accel-pppd.pid
ExecStart=/usr/sbin/accel-pppd -d -p /var/run/accel-pppd.pid -c /etc/accel-ppp.conf
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
ACCELUNIT
    systemctl daemon-reload
    _ok "accel-ppp systemd unit created"

    systemctl enable accel-ppp >/dev/null 2>&1 || true
    _ok "accel-ppp enabled (will start on boot)"
    _info "Review /etc/accel-ppp.conf and start with: systemctl start accel-ppp"
}

_ensure_accel_config() {
    if [[ -f /etc/accel-ppp.conf ]]; then
        _ok "accel-ppp config exists (/etc/accel-ppp.conf)"
        return
    fi

    mkdir -p /etc/accel-ppp.d

    cat > /etc/accel-ppp.conf <<'ACCELCONF'
# =============================================================================
#  accel-ppp.conf — PPPoE/PPTP/L2TP BNG Configuration
#  Generated by dawos-agent installer
#
#  ★ QUICK START — edit these 4 things, then: systemctl start accel-ppp
#    1. [pppoe]  interface=<your-wan-interface>   (e.g. eth1, ens192)
#    2. [dns]    dns1/dns2                        (your DNS servers)
#    3. [ip-pool] subscriber IP range             (e.g. 10.10.0.2-10.10.255.254)
#    4. [radius] server=<ip>,<secret>             (or use [chap-secrets] for local auth)
#
#  Docs: https://accel-ppp.org/documentation/configuration.html
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# MODULES — load only what you need; comment out unused protocols
# ─────────────────────────────────────────────────────────────────────────────
[modules]

# --- Logging (pick one or more) ---
log_file                    # Log to files (see [log] section)
log_syslog                  # Log to syslog (optional, can use both)
# log_tcp                   # Log over TCP to remote collector
# log_pgsql                 # Log to PostgreSQL database

# --- Connection protocols (enable what you serve) ---
pppoe                       # PPPoE — most common for FTTH/DSL BNG
# pptp                      # PPTP — legacy VPN, enable if needed
# l2tp                      # L2TP — carrier-grade tunneling
# sstp                      # SSTP — Microsoft VPN over HTTPS
# ipoe                      # IPoE — IP over Ethernet (DHCP-based, no PPP)

# --- Authentication methods ---
auth_mschap_v2              # MS-CHAPv2 — recommended, supports MPPE
auth_mschap_v1              # MS-CHAPv1 — legacy Windows clients
auth_chap_md5               # CHAP-MD5 — standard CHAP
auth_pap                    # PAP — plaintext (use only over secure links)

# --- Backend & services ---
radius                      # RADIUS authentication & accounting
chap-secrets                # Local file-based auth (/etc/ppp/chap-secrets)
ippool                      # Built-in IPv4 address pool
# ipv6pool                  # Built-in IPv6 address pool
# ipv6_dhcp                 # IPv6 DHCPv6

# --- Traffic control ---
shaper                      # Per-session traffic shaping (tc-based)
# connlimit                 # Connection rate limiting per source

# --- Process management ---
sigchld                     # Required for pppd_compat scripts
pppd_compat                 # Run ip-up/ip-down scripts on session events


# ─────────────────────────────────────────────────────────────────────────────
# CORE — worker threads and error logging
# ─────────────────────────────────────────────────────────────────────────────
[core]
log-error=/var/log/accel-ppp/core.log
# Match to CPU core count for best performance
thread-count=4


# ─────────────────────────────────────────────────────────────────────────────
# COMMON — global session parameters
# ─────────────────────────────────────────────────────────────────────────────
[common]
# If same user connects twice: replace | deny
single-session=replace
# max-sessions=0            # 0=unlimited, set to cap total sessions
# max-starting=0            # 0=unlimited, cap concurrent session setup
# session-timeout=0         # Max session lifetime in seconds (0=infinite)
                            # Can be overridden by RADIUS Session-Timeout


# ─────────────────────────────────────────────────────────────────────────────
# PPP — Point-to-Point Protocol parameters
# ─────────────────────────────────────────────────────────────────────────────
[ppp]
# 0=quiet, 1=log PPP negotiation events
verbose=1
# Reject clients requesting MTU below this
min-mtu=1280
# Negotiated MTU (PPPoE max theoretical: 1492)
mtu=1400
# Maximum Receive Unit
mru=1400
# 0=disable CCP (compression), saves CPU
ccp=0
# Prevent duplicate IP assignment
check-ip=1
# MPPE encryption: require | prefer | deny | allow
# require = reject clients without MPPE support
mppe=require

# --- LCP Echo (keepalive) ---
# Send echo-request every N seconds (0=disable)
lcp-echo-interval=30
# Disconnect after N missed echo-replies
lcp-echo-failure=3
# lcp-echo-timeout=120      # Alternative: disconnect on N seconds of silence

# --- Advanced ---
# ipv4=require              # IPv4 negotiation: deny | allow | prefer | require
# ipv6=deny                 # IPv6 negotiation: deny | allow | prefer | require
# unit-cache=1000           # Cache PPP units for faster reconnection
# unit-preallocate=0        # 1=allocate unit before auth (NAS-Port available)


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — authentication timeouts
# ─────────────────────────────────────────────────────────────────────────────
[auth]
# timeout=10                # Seconds to wait for auth response
# max-failure=3             # Max auth failures before disconnect
# any-login=0               # 1=allow any username (PAP/CHAP/MSCHAPv1)
# noauth=0                  # 1=skip all authentication entirely


# ─────────────────────────────────────────────────────────────────────────────
# PPPoE — ★ most ISPs use this for FTTH/DSL subscribers
# ─────────────────────────────────────────────────────────────────────────────
[pppoe]
verbose=1

# ★ REQUIRED: set your WAN-facing interface(s)
# interface=eth1                         # Single interface
# interface=eth1,padi-limit=100          # With PADI rate limit
# interface=re:eth[2-4]                  # Regex: match eth2, eth3, eth4
# interface=re:vlan.*                    # Regex: all VLAN interfaces

# ac-name=dawos-bng                      # Access Concentrator name (in PADO)
# service-name=internet                  # Service name filter (omit=accept all)
# pado-delay=0                           # PADO delay in ms (load balancing)
# pado-delay=0,300:100                   # No delay up to 100 sessions, then 300ms
# mac-filter=/etc/accel-ppp.d/mac.list,deny  # MAC blacklist/whitelist

# called-sid=mac                         # Called-Station-ID: mac | ifname | ifname:mac
# padi-limit=0                           # Global PADI rate limit/sec (0=unlimited)
# session-timeout=0                      # Override session timeout for PPPoE

# --- VLAN monitoring (dynamic VLAN discovery) ---
# vlan-mon=eth0,10-100                   # Monitor VLANs 10-100 on eth0
# vlan-timeout=60                        # Remove inactive VLANs after N seconds
# vlan-name=%I.%N                        # VLAN name pattern (%I=parent, %N=vlan-id)


# ─────────────────────────────────────────────────────────────────────────────
# PPTP — Point-to-Point Tunneling Protocol (legacy VPN)
# ─────────────────────────────────────────────────────────────────────────────
# [pptp]
# verbose=1
# bind=0.0.0.0                           # Listen address
# port=1723                              # Listen port
# echo-interval=30                       # Keepalive interval
# echo-failure=3                         # Max missed keepalives
# mppe=require                           # MPPE: require | prefer | deny | allow
# ppp-max-mtu=1436                       # Max MTU over PPTP


# ─────────────────────────────────────────────────────────────────────────────
# L2TP — Layer 2 Tunneling Protocol
# ─────────────────────────────────────────────────────────────────────────────
# [l2tp]
# verbose=1
# bind=0.0.0.0                           # Listen address
# port=1701                              # Listen port
# host-name=dawos-bng                    # Host-Name AVP
# hello-interval=30                      # Hello keepalive interval
# timeout=60                             # Tunnel negotiation timeout
# secret=                                # Tunnel secret (empty=none)
# ppp-max-mtu=1420                       # Max MTU over L2TP
# recv-window=16                         # Receive window size (1-32768)
# use-ephemeral-ports=0                  # 1=use random source port


# ─────────────────────────────────────────────────────────────────────────────
# DNS — pushed to PPP clients via IPCP
# ─────────────────────────────────────────────────────────────────────────────
[dns]
# Primary DNS (Google)
dns1=8.8.8.8
# Secondary DNS (Google)
dns2=8.8.4.4
# dns1=1.1.1.1              # Alternative: Cloudflare
# dns2=1.0.0.1

# [ipv6-dns]                             # IPv6 DNS (for IPv6-enabled sessions)
# dns=2001:4860:4860::8888
# dns=2001:4860:4860::8844


# ─────────────────────────────────────────────────────────────────────────────
# IP-POOL — subscriber address assignment
# ─────────────────────────────────────────────────────────────────────────────
[ip-pool]
# Gateway address (BNG's PPP interface address)
gw=10.0.0.1
# shuffle=1                  # 1=randomize IP assignment order

# ★ REQUIRED: define at least one pool range
# Format: <start-ip>-<end-ip>[,name=<pool-name>]
# Format: <network>/<mask>[,name=<pool-name>]

# --- Example: single /16 pool ---
# 10.10.0.2-10.10.255.254,name=main

# --- Example: multiple named pools ---
# 10.10.0.2-10.10.127.254,name=residential
# 10.10.128.2-10.10.255.254,name=business

# --- Example: CIDR notation ---
# 172.16.0.0/22,name=pool1

# attr=Framed-Pool                       # RADIUS attribute for pool selection
# vendor=                                # Vendor name for vendor-specific attr


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING — file, syslog, per-session/per-user logs
# ─────────────────────────────────────────────────────────────────────────────
[log]
log-file=/var/log/accel-ppp/accel-ppp.log
log-emerg=/var/log/accel-ppp/emerg.log
log-fail-file=/var/log/accel-ppp/auth-fail.log
# 1=duplicate per-session logs into main log
copy=1
# 0=off, 1=error, 2=+warn, 3=+info, 4=+full, 5=+debug
level=3

# --- Per-session/per-user logs (for troubleshooting) ---
# per-user-dir=/var/log/accel-ppp/users
# per-session-dir=/var/log/accel-ppp/sessions
# per-session=1              # 1=separate file per session under per-user-dir


# ─────────────────────────────────────────────────────────────────────────────
# CLI — command-line interface for accel-cmd
#
# ★ IMPORTANT: use tcp= (not telnet=) to avoid negotiation issues
#   with accel-cmd. telnet= works for interactive use but can hang
#   when accel-cmd sends commands programmatically.
# ─────────────────────────────────────────────────────────────────────────────
[cli]
# TCP listener (used by accel-cmd and dawos-agent)
tcp=127.0.0.1:2001
# telnet=127.0.0.1:2002     # Telnet listener (interactive admin only)
# password=                  # Omit or comment out for no authentication
# verbose=1                  # 1=log connection IPs, 2=also log commands

# --- Default columns for "show sessions" ---
# sessions-columns=ifname,username,calling-sid,ip,rate-limit,type,comp,state,uptime


# ─────────────────────────────────────────────────────────────────────────────
# RADIUS — authentication, authorization, and accounting
# ─────────────────────────────────────────────────────────────────────────────
[radius]
verbose=1

# ★ REQUIRED (if using RADIUS): define at least one server
# Format: server=<ip>,<secret>[,auth-port=N][,acct-port=N][,weight=N][,backup]

# --- Example: single RADIUS server ---
# server=10.0.0.100,my-radius-secret,auth-port=1812,acct-port=1813

# --- Example: primary + backup ---
# server=10.0.0.100,secret1,weight=2
# server=10.0.0.101,secret2,weight=1,backup

# --- NAS identification ---
# nas-identifier=dawos-bng               # NAS-Identifier attribute
# nas-ip-address=10.0.0.1                # NAS-IP-Address attribute

# --- Timeouts and retries ---
# Seconds to wait for RADIUS response
timeout=3
# Max retries for auth/acct requests
max-try=3
# Accounting interim update timeout
acct-timeout=120

# --- Accounting ---
# acct-interim-interval=300              # Interim accounting updates (seconds)
# acct-interim-jitter=60                 # Randomize interim timing (seconds)
# acct-delay-time=0                      # 1=include Acct-Delay-Time
# acct-on=0                              # 1=send Accounting-On at startup

# --- Dynamic Authorization (CoA/DM) ---
# dae-server=127.0.0.1:3799,secret      # DAE listener for CoA/Disconnect
# dae-allowed=10.0.0.100                 # Allowed DAE source IPs

# --- Username handling ---
# default-realm=example.com              # Append realm if none present
# strip-realm=0                          # 1=remove @realm from username
# sid-in-auth=0                          # 1=send session-id in Access-Request


# ─────────────────────────────────────────────────────────────────────────────
# CHAP-SECRETS — local file-based authentication
#   Alternative to RADIUS. Uses /etc/ppp/chap-secrets format:
#   username  server  password  ip-address
# ─────────────────────────────────────────────────────────────────────────────
[chap-secrets]
# chap-secrets=/etc/ppp/chap-secrets     # Auth file path
# gw-ip-address=10.0.0.1                 # Local PPP address for chap-secrets auth
# encrypted=0                            # 1=passwords are hashed


# ─────────────────────────────────────────────────────────────────────────────
# SHAPER — per-session traffic shaping
#
# Rate format from RADIUS/chap-secrets:
#   Filter-Id = "10000/5000"  → 10Mbps down, 5Mbps up (in Kbit/s)
#   Filter-Id = "10M/5M"     → same, with suffix
# ─────────────────────────────────────────────────────────────────────────────
[shaper]
verbose=1
# RADIUS attribute containing rate info
attr=Filter-Id
# attr-down=PPPD-Downstream-Speed-Limit  # Alternative: separate down attribute
# attr-up=PPPD-Upstream-Speed-Limit      # Alternative: separate up attribute

# Upstream method: police | htb
up-limiter=police
# Downstream method: tbf | htb | clsact
down-limiter=tbf

# rate-limit=100000/50000                # Default rate (Kbit/s) if not from RADIUS
# burst-factor=0.1                       # Burst = rate × factor
# up-burst-factor=0.1                    # Upstream burst factor
# down-burst-factor=0.1                  # Downstream burst factor
# latency=50                             # TBF latency parameter (ms)
# r2q=10                                 # HTB r2q parameter
# leaf-qdisc=sfq perturb 10              # Leaf qdisc: sfq or fq_codel
# fwmark=1                               # Skip shaping for marked packets


# ─────────────────────────────────────────────────────────────────────────────
# PPPD-COMPAT — run scripts on session events
#   Scripts receive env vars: PEERNAME, IPLOCAL, IPREMOTE, SPEED, etc.
#   See pppd(8) for full list of available variables.
# ─────────────────────────────────────────────────────────────────────────────
[pppd-compat]
ip-up=/etc/accel-ppp.d/ip-up
ip-down=/etc/accel-ppp.d/ip-down
# ip-pre-up=/etc/accel-ppp.d/ip-pre-up  # Called before interface comes up
# ip-change=/etc/accel-ppp.d/ip-change  # Called on RADIUS CoA
# radattr-prefix=/var/run/radattr       # Write RADIUS attrs to file
# verbose=1


# ─────────────────────────────────────────────────────────────────────────────
# CONNLIMIT — rate-limit new connections from a single source
# ─────────────────────────────────────────────────────────────────────────────
# [connlimit]
# limit=1/s                              # Max 1 connection/second per source
# burst=3                                # Allow burst of 3
# timeout=10                             # Pause checking after timeout


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT-IP-RANGE — restrict source IP ranges (optional security)
# ─────────────────────────────────────────────────────────────────────────────
# [client-ip-range]
# 10.0.0.0/8
# 172.16.0.0/12
# 192.168.0.0/16
ACCELCONF

    # Create log directory and hook scripts
    mkdir -p /var/log/accel-ppp
    touch /etc/accel-ppp.d/ip-up /etc/accel-ppp.d/ip-down
    chmod +x /etc/accel-ppp.d/ip-up /etc/accel-ppp.d/ip-down

    _ok "Starter config written to /etc/accel-ppp.conf"
    _warn "You MUST edit /etc/accel-ppp.conf before starting accel-ppp"
}

# =============================================================================
#  DOWNLOAD
# =============================================================================
_download_source() {
    _header "DOWNLOAD" "Downloading source"

    # Check if running from within the repo already
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"

    if [[ -f "${script_dir}/pyproject.toml" ]]; then
        SOURCE_DIR="$script_dir"
        _ok "Source found locally (${SOURCE_DIR})"
        return
    elif [[ -f "${script_dir}/../pyproject.toml" ]]; then
        SOURCE_DIR="$(cd "${script_dir}/.." && pwd)"
        _ok "Source found locally (${SOURCE_DIR})"
        return
    fi

    # Download from GitHub
    _step "Downloading from ${REPO_URL}..."

    if ! command -v curl &>/dev/null; then
        _fatal "curl is required to download the source. Install it: apt-get install curl"
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d /tmp/dawos-agent-install.XXXXXX)
    trap "_spin_stop; rm -rf '${tmp_dir}'" EXIT

    _spin_start "Downloading ${REPO_NAME} (${REPO_BRANCH})..."
    if curl -sL "$TARBALL_URL" | tar xz -C "$tmp_dir" 2>/dev/null; then
        _spin_stop
        SOURCE_DIR="${tmp_dir}/${REPO_NAME}-${REPO_BRANCH}"
        if [[ -f "${SOURCE_DIR}/pyproject.toml" ]]; then
            _ok "Downloaded and extracted to ${SOURCE_DIR}"
        else
            _fatal "Download succeeded but pyproject.toml not found"
        fi
    else
        _spin_stop
        _fatal "Failed to download from ${TARBALL_URL}"
    fi
}

# =============================================================================
#  INSTALL
# =============================================================================
_install_package() {
    _header "INSTALL" "Installing dawos-agent"

    local repo_dir="$SOURCE_DIR"

    if [[ ! -f "${repo_dir}/pyproject.toml" ]]; then
        _fatal "Source directory invalid — pyproject.toml not found in ${repo_dir}"
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
#  SERVICE
# =============================================================================
_install_service() {
    _header "SERVICE" "Service & security"

    local repo_dir="$SOURCE_DIR"

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
# dawos-agent — passwordless sudo for router management
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
Description=dawos-agent — PPP router management daemon
Documentation=https://github.com/Cepat-Kilat-Teknologi/dawos-agent
After=network-online.target accel-ppp.service
Wants=network-online.target
StartLimitBurst=3
StartLimitIntervalSec=60

[Service]
Type=simple
User=dawos
Group=dawos
EnvironmentFile=-/etc/dawos-agent/agent.env
ExecStart=/opt/dawos-agent/venv/bin/dawos-agent
Restart=on-failure
RestartSec=5

NoNewPrivileges=false
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=-/etc/accel-ppp.conf -/etc/accel-ppp.d -/etc/accel-nat-egress.nft -/etc/sysctl.d -/etc/nftables.conf
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
#  VERIFY
# =============================================================================
_health_check() {
    _header "VERIFY" "Verification"

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
    _install_accel_ppp
    # Safety net: ensure accel-ppp systemd unit exists even if
    # _install_accel_ppp took the "already installed" short path.
    _ensure_accel_service
    _download_source
    _install_package
    _install_service
    _health_check
    _summary
}

main "$@"
