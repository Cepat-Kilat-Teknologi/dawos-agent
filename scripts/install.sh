#!/usr/bin/env bash
# install.sh — minimal dawos-agent installer (no interactive prompts)
# Usage: sudo bash scripts/install.sh
#
# NOTE: For a full interactive installer with TUI wizard, upgrade
# detection, and health checks, use the root-level install.sh instead:
#   sudo bash install.sh
set -euo pipefail

# ── constants ───────────────────────────────────────────────────────
APP_NAME="dawos-agent"
APP_USER="dawos"
APP_GROUP="dawos"
INSTALL_DIR="/opt/dawos-agent"
VENV_DIR="${INSTALL_DIR}/venv"
CONFIG_DIR="/etc/dawos-agent"
ENV_FILE="${CONFIG_DIR}/agent.env"
SYSTEMD_UNIT="/etc/systemd/system/${APP_NAME}.service"
SUDOERS_FILE="/etc/sudoers.d/${APP_NAME}"

# ── colours ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── pre-flight ──────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "Run as root: sudo bash $0"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

[[ -f "${REPO_DIR}/pyproject.toml" ]] || error "Cannot find pyproject.toml — run from the dawos-agent repo"

info "Installing ${APP_NAME} from ${REPO_DIR}"

# ── 1. system user ─────────────────────────────────────────────────
if id "${APP_USER}" &>/dev/null; then
    info "User '${APP_USER}' already exists"
else
    useradd --system --shell /usr/sbin/nologin --home-dir "${INSTALL_DIR}" "${APP_USER}"
    info "Created system user '${APP_USER}'"
fi

# Add to systemd-journal group so journalctl works without sudo
if getent group systemd-journal &>/dev/null; then
    usermod -aG systemd-journal "${APP_USER}" 2>/dev/null || true
    info "Added '${APP_USER}' to systemd-journal group"
fi

# ── 2. install directory + venv ────────────────────────────────────
mkdir -p "${INSTALL_DIR}"
mkdir -p /var/lib/dawos-agent
chown "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}"
chown "${APP_USER}:${APP_GROUP}" /var/lib/dawos-agent

if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
    info "Created virtualenv at ${VENV_DIR}"
else
    info "Virtualenv already exists at ${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install "${REPO_DIR}" --quiet
info "Installed ${APP_NAME} into ${VENV_DIR}"

# ── 3. configuration ───────────────────────────────────────────────
mkdir -p "${CONFIG_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
    # Generate a random API key on first install
    API_KEY="$(openssl rand -hex 24)"
    cat > "${ENV_FILE}" <<EOF
# dawos-agent configuration — generated $(date -u +%Y-%m-%dT%H:%M:%SZ)

# API authentication key — share with dawu-radius
DAWOS_API_KEY=${API_KEY}

# Agent listen address
DAWOS_HOST=0.0.0.0
DAWOS_PORT=8470

# Node identity (auto-detected from hostname if empty)
DAWOS_NODE_NAME=

# accel-ppp settings
ACCEL_CMD=/usr/bin/accel-cmd
ACCEL_CLI_PORT=2001
ACCEL_CONFIG_PATH=/etc/accel-ppp.conf
ACCEL_SERVICE_NAME=accel-ppp

# Logging
DAWOS_LOG_LEVEL=info
EOF
    chmod 0640 "${ENV_FILE}"
    chown root:"${APP_GROUP}" "${ENV_FILE}"
    info "Created ${ENV_FILE} with generated API key"
    warn "Save this API key: ${API_KEY}"
else
    info "Config ${ENV_FILE} already exists — skipping"
fi

# ── 4. sudoers ──────────────────────────────────────────────────────
cp "${REPO_DIR}/deploy/dawos-agent.sudoers" "${SUDOERS_FILE}"
chmod 0440 "${SUDOERS_FILE}"

if visudo -cf "${SUDOERS_FILE}" &>/dev/null; then
    info "Installed sudoers file at ${SUDOERS_FILE}"
else
    rm -f "${SUDOERS_FILE}"
    error "Sudoers syntax check failed — removed ${SUDOERS_FILE}"
fi

# ── 5. systemd unit ────────────────────────────────────────────────
cp "${REPO_DIR}/systemd/dawos-agent.service" "${SYSTEMD_UNIT}"
systemctl daemon-reload
info "Installed systemd unit"

# Enable but don't start yet — user should verify config first
systemctl enable "${APP_NAME}" 2>/dev/null || true
info "Enabled ${APP_NAME} (not started yet)"

# ── 6. summary ─────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ${APP_NAME} installed successfully!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "  Config:    ${ENV_FILE}"
echo "  Venv:      ${VENV_DIR}"
echo "  Sudoers:   ${SUDOERS_FILE}"
echo "  Service:   ${SYSTEMD_UNIT}"
echo ""
echo "  Next steps:"
echo "    1. Review config:   sudo nano ${ENV_FILE}"
echo "    2. Start service:   sudo systemctl start ${APP_NAME}"
echo "    3. Check status:    sudo systemctl status ${APP_NAME}"
echo "    4. View logs:       journalctl -u ${APP_NAME} -f"
echo "    5. Test API:        curl -H 'X-API-Key: <key>' http://localhost:8470/api/v1/health"
echo ""
