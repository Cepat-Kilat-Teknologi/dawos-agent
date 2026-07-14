#!/usr/bin/env bash
# manage.sh — dawos-agent upgrade / downgrade / rollback manager
# Usage:
#   sudo bash scripts/manage.sh upgrade                  # upgrade to latest PyPI
#   sudo bash scripts/manage.sh upgrade 0.2.0            # upgrade to specific version
#   sudo bash scripts/manage.sh upgrade --git            # upgrade from GitHub main
#   sudo bash scripts/manage.sh upgrade --git v0.2.0     # upgrade from GitHub tag
#   sudo bash scripts/manage.sh upgrade --git feat/xyz   # upgrade from GitHub branch
#   sudo bash scripts/manage.sh downgrade 0.0.9          # downgrade to specific version
#   sudo bash scripts/manage.sh rollback                 # rollback to previous version
#   sudo bash scripts/manage.sh status                   # show current install info
#   sudo bash scripts/manage.sh verify                   # run post-deploy verification
#   sudo bash scripts/manage.sh history                  # show upgrade/downgrade history
set -euo pipefail

# ── constants ────────────────────────────────────────────────────────
APP_NAME="dawos-agent"
APP_USER="dawos"
APP_GROUP="dawos"
INSTALL_DIR="/opt/dawos-agent"
VENV_DIR="${INSTALL_DIR}/venv"
PIP="${VENV_DIR}/bin/pip"
CONFIG_DIR="/etc/dawos-agent"
ENV_FILE="${CONFIG_DIR}/agent.env"
BACKUP_DIR="${INSTALL_DIR}/backups"
HISTORY_FILE="${INSTALL_DIR}/upgrade-history.log"
SUDOERS_FILE="/etc/sudoers.d/${APP_NAME}"
HEALTH_URL="http://localhost:8470/health"
GITHUB_REPO="https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git"
MAX_BACKUPS=10
HEALTH_TIMEOUT=10
HEALTH_RETRIES=5

# ── colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*" >&2; }
warn()  { echo -e "${YELLOW}[!]${NC} $*" >&2; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }
die()   { error "$*"; exit 1; }
step()  { echo -e "${BLUE}[→]${NC} $*" >&2; }
header(){ echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}\n" >&2; }

# ── pre-flight ───────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash $0 <command> [args]"
[[ -d "${VENV_DIR}" ]] || die "Virtualenv not found at ${VENV_DIR} — run install.sh first"
[[ -x "${PIP}" ]] || die "pip not found at ${PIP}"

# ── helpers ──────────────────────────────────────────────────────────

get_installed_version() {
    "${PIP}" show "${APP_NAME}" 2>/dev/null | grep -i "^Version:" | awk '{print $2}' || echo "unknown"
}

get_installed_source() {
    local location
    location=$("${PIP}" show "${APP_NAME}" 2>/dev/null | grep -i "^Location:" | awk '{print $2}')
    if [[ -z "${location}" ]]; then
        echo "not-installed"
    else
        echo "${location}"
    fi
}

get_running_version() {
    local response
    response=$(curl -sf --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" 2>/dev/null) || { echo "offline"; return; }
    echo "${response}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','unknown'))" 2>/dev/null || echo "unknown"
}

wait_for_health() {
    local retries=$1
    local delay=2
    step "Waiting for service health (max ${retries} attempts)..."
    for i in $(seq 1 "${retries}"); do
        if curl -sf --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" >/dev/null 2>&1; then
            info "Service healthy (attempt ${i}/${retries})"
            return 0
        fi
        sleep "${delay}"
    done
    error "Service did not become healthy after ${retries} attempts"
    return 1
}

backup_current() {
    local version
    version=$(get_installed_version)
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_name="${version}_${timestamp}"
    local backup_path="${BACKUP_DIR}/${backup_name}"

    mkdir -p "${BACKUP_DIR}"

    step "Backing up current installation (v${version})..."

    # Save wheel for rollback
    "${PIP}" wheel "${APP_NAME}==${version}" \
        --wheel-dir="${backup_path}" \
        --no-deps --quiet 2>/dev/null || {
        # If PyPI wheel unavailable, freeze the installed package
        mkdir -p "${backup_path}"
        "${PIP}" freeze | grep -i "${APP_NAME}" > "${backup_path}/requirements.txt" 2>/dev/null || true
    }

    # Save version metadata
    cat > "${backup_path}/metadata.txt" <<EOF
version=${version}
timestamp=${timestamp}
source=$(get_installed_source)
python=$("${VENV_DIR}/bin/python" --version 2>&1)
EOF

    info "Backup saved to ${backup_path}"

    # Rotate old backups (keep MAX_BACKUPS)
    local count
    count=$(find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | wc -l)
    if [[ ${count} -gt ${MAX_BACKUPS} ]]; then
        find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d \
            | sort | head -n $((count - MAX_BACKUPS)) \
            | xargs rm -rf
        info "Rotated old backups (kept last ${MAX_BACKUPS})"
    fi

    echo "${backup_path}"
}

log_history() {
    local action="$1"
    local from_version="$2"
    local to_version="$3"
    local source="$4"
    local status="$5"
    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "${timestamp} | ${action} | ${from_version} → ${to_version} | source=${source} | ${status}" >> "${HISTORY_FILE}"
}

fix_ownership() {
    step "Fixing file ownership..."
    chown -R "${APP_USER}:${APP_GROUP}" "${INSTALL_DIR}"

    # Ensure history database directory exists (added in v0.4.0)
    if [[ ! -d /var/lib/dawos-agent ]]; then
        mkdir -p /var/lib/dawos-agent
    fi
    chown "${APP_USER}:${APP_GROUP}" /var/lib/dawos-agent

    # Fix accel-ppp config ownership (required for config backup operations)
    if [[ -d /etc/accel-ppp.d ]]; then
        chown -R "${APP_USER}:${APP_GROUP}" /etc/accel-ppp.d/
    fi
    if [[ -f /etc/accel-ppp.conf ]]; then
        chown "${APP_USER}:${APP_GROUP}" /etc/accel-ppp.conf
    fi

    info "Ownership fixed"
}

update_sudoers() {
    # Check if sudoers needs updating from the installed package
    local pkg_sudoers
    pkg_sudoers=$("${VENV_DIR}/bin/python" -c "
import importlib.resources, pathlib
try:
    ref = importlib.resources.files('dawos_agent').joinpath('../deploy/dawos-agent.sudoers')
    print(ref)
except Exception:
    pass
" 2>/dev/null) || true

    # If we have a sudoers file from the repo, compare and update
    local script_dir
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    local repo_sudoers="${script_dir}/../deploy/dawos-agent.sudoers"

    if [[ -f "${repo_sudoers}" ]]; then
        if ! diff -q "${repo_sudoers}" "${SUDOERS_FILE}" >/dev/null 2>&1; then
            step "Updating sudoers rules..."
            cp "${repo_sudoers}" "${SUDOERS_FILE}"
            chmod 0440 "${SUDOERS_FILE}"
            if visudo -cf "${SUDOERS_FILE}" &>/dev/null; then
                info "Sudoers updated"
            else
                warn "Sudoers syntax check failed — reverting"
                rm -f "${SUDOERS_FILE}"
            fi
        fi
    fi
}

update_systemd_unit() {
    # Migrate systemd unit ReadWritePaths for v0.4.0+ (session history DB)
    local unit="/etc/systemd/system/${APP_NAME}.service"
    if [[ ! -f "${unit}" ]]; then
        return
    fi

    if ! grep -q "/var/lib/dawos-agent" "${unit}" 2>/dev/null; then
        step "Adding /var/lib/dawos-agent to systemd ReadWritePaths..."
        sed -i 's|^ReadWritePaths=.*|& -/var/lib/dawos-agent|' "${unit}"
        systemctl daemon-reload
        info "Systemd unit updated (ReadWritePaths)"
    fi
}

do_verify() {
    header "Post-Deploy Verification"

    local errors=0

    # 1. Service running
    step "Checking systemd service..."
    if systemctl is-active "${APP_NAME}" >/dev/null 2>&1; then
        info "Service active"
    else
        error "Service not active"
        ((errors++))
    fi

    # 2. Health endpoint
    step "Checking health endpoint..."
    local health_response
    health_response=$(curl -sf --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" 2>/dev/null) || {
        error "Health endpoint unreachable"
        ((errors++))
        health_response=""
    }
    if [[ -n "${health_response}" ]]; then
        local health_status
        health_status=$(echo "${health_response}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
        if [[ "${health_status}" == "ok" ]]; then
            info "Health: OK"
            echo "    ${health_response}" | python3 -m json.tool 2>/dev/null || echo "    ${health_response}"
        else
            error "Health status: ${health_status}"
            ((errors++))
        fi
    fi

    # 3. Auth rejection (no API key → 401)
    step "Checking auth rejection..."
    local auth_code
    auth_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time "${HEALTH_TIMEOUT}" \
        "http://localhost:8470/api/v1/sessions" 2>/dev/null) || auth_code="000"
    if [[ "${auth_code}" == "401" ]]; then
        info "Auth rejection: 401 (correct)"
    else
        error "Auth rejection: expected 401, got ${auth_code}"
        ((errors++))
    fi

    # 4. Authenticated call (if API key available)
    step "Checking authenticated endpoint..."
    local api_key=""
    if [[ -f "${ENV_FILE}" ]]; then
        api_key=$(grep -E "^DAWOS_API_KEY=" "${ENV_FILE}" 2>/dev/null | cut -d= -f2 | tr -d '"' | tr -d "'" | xargs)
    fi
    if [[ -n "${api_key}" ]]; then
        local auth_response
        auth_response=$(curl -sf --max-time "${HEALTH_TIMEOUT}" \
            -H "X-API-Key: ${api_key}" \
            "http://localhost:8470/api/v1/sessions" 2>/dev/null) || {
            error "Authenticated call failed"
            ((errors++))
            auth_response=""
        }
        if [[ -n "${auth_response}" ]]; then
            info "Authenticated call: OK"
        fi
    else
        warn "No API key found in ${ENV_FILE} — skipping auth test"
    fi

    # 5. accel-ppp integration
    step "Checking accel-ppp integration..."
    if command -v accel-cmd >/dev/null 2>&1; then
        local accel_version
        accel_version=$(accel-cmd show version 2>/dev/null | head -1) || accel_version=""
        if [[ -n "${accel_version}" ]]; then
            info "accel-ppp: ${accel_version}"
        else
            warn "accel-cmd available but returned empty (accel-ppp may be stopped)"
        fi
    else
        warn "accel-cmd not found (accel-ppp not installed on this node)"
    fi

    # 6. Error log check
    step "Checking recent error logs..."
    local error_count
    error_count=$(journalctl -u "${APP_NAME}" --since "2 minutes ago" --no-pager -p err 2>/dev/null | grep -c "" || echo "0")
    if [[ "${error_count}" -le 1 ]]; then
        info "No recent errors in journal"
    else
        warn "Found ${error_count} error lines in journal (last 2 min)"
        journalctl -u "${APP_NAME}" --since "2 minutes ago" --no-pager -p err 2>/dev/null | tail -5
    fi

    # 7. Pip check (dependency conflicts)
    step "Checking dependency integrity..."
    local pip_check
    pip_check=$("${PIP}" check 2>&1) || true
    if echo "${pip_check}" | grep -qi "no broken"; then
        info "No broken dependencies"
    elif [[ -z "${pip_check}" ]]; then
        info "Dependencies OK"
    else
        warn "Dependency issues: ${pip_check}"
    fi

    echo ""
    if [[ ${errors} -eq 0 ]]; then
        echo -e "${GREEN}${BOLD}All verification checks passed ✓${NC}"
    else
        echo -e "${RED}${BOLD}${errors} verification check(s) failed ✗${NC}"
    fi
    return ${errors}
}

# ── commands ─────────────────────────────────────────────────────────

cmd_status() {
    header "dawos-agent Status"

    local installed_ver running_ver source_loc
    installed_ver=$(get_installed_version)
    running_ver=$(get_running_version)
    source_loc=$(get_installed_source)
    local service_state
    service_state=$(systemctl is-active "${APP_NAME}" 2>/dev/null || echo "unknown")
    local python_ver
    python_ver=$("${VENV_DIR}/bin/python" --version 2>&1)

    echo -e "  ${BOLD}Installed version:${NC}  ${installed_ver}"
    echo -e "  ${BOLD}Running version:${NC}    ${running_ver}"
    echo -e "  ${BOLD}Service state:${NC}      ${service_state}"
    echo -e "  ${BOLD}Python:${NC}             ${python_ver}"
    echo -e "  ${BOLD}Venv:${NC}               ${VENV_DIR}"
    echo -e "  ${BOLD}Packages:${NC}           ${source_loc}"
    echo -e "  ${BOLD}Config:${NC}             ${ENV_FILE}"
    echo -e "  ${BOLD}Sudoers:${NC}            ${SUDOERS_FILE}"
    echo ""

    # Show available PyPI versions
    step "Available versions on PyPI..."
    "${PIP}" index versions "${APP_NAME}" 2>/dev/null | head -3 || warn "Cannot query PyPI"

    # Show backup count
    if [[ -d "${BACKUP_DIR}" ]]; then
        local backup_count
        backup_count=$(find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | wc -l)
        echo -e "\n  ${BOLD}Backups:${NC}            ${backup_count} (in ${BACKUP_DIR})"
    fi
}

cmd_upgrade() {
    local use_git=false
    local target_ref=""
    local target_version=""

    # Parse args
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --git|-g)
                use_git=true
                shift
                if [[ $# -gt 0 && ! "$1" =~ ^- ]]; then
                    target_ref="$1"
                    shift
                fi
                ;;
            *)
                target_version="$1"
                shift
                ;;
        esac
    done

    local old_version
    old_version=$(get_installed_version)

    header "Upgrade dawos-agent"

    if ${use_git}; then
        local ref="${target_ref:-main}"
        echo -e "  ${BOLD}Source:${NC}    GitHub (${GITHUB_REPO})"
        echo -e "  ${BOLD}Ref:${NC}      ${ref}"
    else
        local ver_display="${target_version:-latest}"
        echo -e "  ${BOLD}Source:${NC}    PyPI"
        echo -e "  ${BOLD}Target:${NC}   ${ver_display}"
    fi
    echo -e "  ${BOLD}Current:${NC}  ${old_version}"
    echo ""

    # 1. Backup
    local backup_path
    backup_path=$(backup_current)

    # 2. Stop service gracefully
    step "Stopping ${APP_NAME} service..."
    systemctl stop "${APP_NAME}" 2>/dev/null || true
    info "Service stopped"

    # 3. Perform upgrade
    local install_status=0
    if ${use_git}; then
        local ref="${target_ref:-main}"
        step "Installing from GitHub (ref: ${ref})..."
        "${PIP}" install --force-reinstall --no-deps --no-cache-dir \
            "git+${GITHUB_REPO}@${ref}" 2>&1 | tail -5 || install_status=$?
    else
        if [[ -n "${target_version}" ]]; then
            step "Installing ${APP_NAME}==${target_version} from PyPI..."
            "${PIP}" install --no-cache-dir \
                "${APP_NAME}==${target_version}" 2>&1 | tail -5 || install_status=$?
        else
            step "Upgrading to latest from PyPI..."
            "${PIP}" install --upgrade --no-cache-dir \
                "${APP_NAME}" 2>&1 | tail -5 || install_status=$?
        fi
    fi

    if [[ ${install_status} -ne 0 ]]; then
        error "Installation failed — rolling back..."
        _do_rollback_from "${backup_path}" "${old_version}"
        log_history "upgrade" "${old_version}" "failed" "$(${use_git} && echo 'github' || echo 'pypi')" "FAILED"
        die "Upgrade failed and was rolled back to v${old_version}"
    fi

    local new_version
    new_version=$(get_installed_version)
    info "Installed v${new_version}"

    # 4. Fix ownership
    fix_ownership

    # 4b. Migrate sudoers and systemd unit if needed (v0.4.0+ history DB)
    update_sudoers
    update_systemd_unit

    # 5. Start service
    step "Starting ${APP_NAME} service..."
    systemctl start "${APP_NAME}"

    # 6. Wait for health
    if ! wait_for_health "${HEALTH_RETRIES}"; then
        error "Service failed health check — rolling back..."
        systemctl stop "${APP_NAME}" 2>/dev/null || true
        _do_rollback_from "${backup_path}" "${old_version}"
        systemctl start "${APP_NAME}"
        wait_for_health 3 || true
        log_history "upgrade" "${old_version}" "${new_version}" "$(${use_git} && echo 'github' || echo 'pypi')" "ROLLBACK"
        die "Upgrade to v${new_version} failed health check — rolled back to v${old_version}"
    fi

    # 7. Log and report
    log_history "upgrade" "${old_version}" "${new_version}" "$(${use_git} && echo 'github' || echo 'pypi')" "OK"

    header "Upgrade Complete"
    echo -e "  ${BOLD}Previous:${NC}  v${old_version}"
    echo -e "  ${BOLD}Current:${NC}   v${new_version}"
    echo -e "  ${BOLD}Backup:${NC}    ${backup_path}"
    echo ""

    # 8. Run verification
    do_verify
}

cmd_downgrade() {
    local target_version="${1:-}"
    [[ -n "${target_version}" ]] || die "Usage: $0 downgrade <version>  (e.g., $0 downgrade 0.0.9)"

    local old_version
    old_version=$(get_installed_version)

    header "Downgrade dawos-agent"
    echo -e "  ${BOLD}Current:${NC}   v${old_version}"
    echo -e "  ${BOLD}Target:${NC}    v${target_version}"
    echo ""

    # 1. Backup current
    local backup_path
    backup_path=$(backup_current)

    # 2. Stop service
    step "Stopping ${APP_NAME} service..."
    systemctl stop "${APP_NAME}" 2>/dev/null || true
    info "Service stopped"

    # 3. Install specific version
    step "Installing ${APP_NAME}==${target_version}..."
    local install_status=0
    "${PIP}" install --force-reinstall --no-deps --no-cache-dir \
        "${APP_NAME}==${target_version}" 2>&1 | tail -5 || install_status=$?

    if [[ ${install_status} -ne 0 ]]; then
        error "Downgrade failed — rolling back..."
        _do_rollback_from "${backup_path}" "${old_version}"
        log_history "downgrade" "${old_version}" "${target_version}" "pypi" "FAILED"
        die "Downgrade failed. Rolled back to v${old_version}"
    fi

    local new_version
    new_version=$(get_installed_version)
    info "Installed v${new_version}"

    # 4. Fix ownership
    fix_ownership

    # 4b. Migrate systemd unit if needed
    update_systemd_unit

    # 5. Start service
    step "Starting ${APP_NAME} service..."
    systemctl start "${APP_NAME}"

    # 6. Wait for health
    if ! wait_for_health "${HEALTH_RETRIES}"; then
        error "Service failed health check after downgrade — rolling back..."
        systemctl stop "${APP_NAME}" 2>/dev/null || true
        _do_rollback_from "${backup_path}" "${old_version}"
        systemctl start "${APP_NAME}"
        wait_for_health 3 || true
        log_history "downgrade" "${old_version}" "${target_version}" "pypi" "ROLLBACK"
        die "Downgrade to v${target_version} failed — rolled back to v${old_version}"
    fi

    log_history "downgrade" "${old_version}" "${new_version}" "pypi" "OK"

    header "Downgrade Complete"
    echo -e "  ${BOLD}Previous:${NC}  v${old_version}"
    echo -e "  ${BOLD}Current:${NC}   v${new_version}"
    echo -e "  ${BOLD}Backup:${NC}    ${backup_path}"
    echo ""

    do_verify
}

cmd_rollback() {
    header "Rollback dawos-agent"

    # Find the most recent backup
    if [[ ! -d "${BACKUP_DIR}" ]]; then
        die "No backups found at ${BACKUP_DIR}"
    fi

    local latest_backup
    latest_backup=$(find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d | sort -r | head -1)
    [[ -n "${latest_backup}" ]] || die "No backup directories found"

    local backup_version="unknown"
    if [[ -f "${latest_backup}/metadata.txt" ]]; then
        backup_version=$(grep "^version=" "${latest_backup}/metadata.txt" | cut -d= -f2)
    fi

    local current_version
    current_version=$(get_installed_version)

    echo -e "  ${BOLD}Current:${NC}   v${current_version}"
    echo -e "  ${BOLD}Rollback:${NC}  v${backup_version} (from ${latest_backup})"
    echo ""

    _do_rollback_from "${latest_backup}" "${backup_version}"

    # Restart service
    step "Restarting ${APP_NAME} service..."
    systemctl restart "${APP_NAME}"
    wait_for_health "${HEALTH_RETRIES}" || true

    log_history "rollback" "${current_version}" "${backup_version}" "backup" "OK"

    header "Rollback Complete"
    echo -e "  ${BOLD}Restored:${NC}  v$(get_installed_version)"
    echo ""

    do_verify
}

_do_rollback_from() {
    local backup_path="$1"
    local target_version="$2"

    step "Rolling back to v${target_version}..."

    # Try to install from backup wheel
    local wheel
    wheel=$(find "${backup_path}" -name "*.whl" 2>/dev/null | head -1)
    if [[ -n "${wheel}" ]]; then
        "${PIP}" install --force-reinstall --no-deps "${wheel}" --quiet 2>/dev/null || {
            # Fallback: install from PyPI
            "${PIP}" install --force-reinstall --no-deps --no-cache-dir \
                "${APP_NAME}==${target_version}" --quiet 2>/dev/null || {
                error "Cannot rollback — both wheel and PyPI install failed"
                return 1
            }
        }
    else
        # No wheel, try PyPI
        "${PIP}" install --force-reinstall --no-deps --no-cache-dir \
            "${APP_NAME}==${target_version}" --quiet 2>/dev/null || {
            error "Cannot rollback from PyPI"
            return 1
        }
    fi

    fix_ownership
    info "Rolled back to v$(get_installed_version)"
}

cmd_history() {
    header "Upgrade/Downgrade History"

    if [[ ! -f "${HISTORY_FILE}" ]]; then
        warn "No history found"
        return
    fi

    echo -e "${BOLD}  Timestamp                | Action     | Versions           | Source  | Status${NC}"
    echo "  ─────────────────────────┼────────────┼────────────────────┼─────────┼────────"
    while IFS='|' read -r ts action versions source status; do
        printf "  %s |%s |%s |%s |%s\n" \
            "$(echo "${ts}" | xargs)" \
            "$(echo "${action}" | xargs)" \
            "$(echo "${versions}" | xargs)" \
            "$(echo "${source}" | xargs)" \
            "$(echo "${status}" | xargs)"
    done < "${HISTORY_FILE}"
    echo ""
}

cmd_verify() {
    do_verify
}

# ── main ─────────────────────────────────────────────────────────────

usage() {
    echo -e "${BOLD}dawos-agent management tool${NC}"
    echo ""
    echo "Usage: sudo bash $0 <command> [options]"
    echo ""
    echo -e "${BOLD}Commands:${NC}"
    echo "  upgrade                     Upgrade to latest PyPI version"
    echo "  upgrade <version>           Upgrade to specific PyPI version"
    echo "  upgrade --git               Upgrade from GitHub main branch"
    echo "  upgrade --git <ref>         Upgrade from GitHub branch/tag/commit"
    echo "  downgrade <version>         Downgrade to specific PyPI version"
    echo "  rollback                    Rollback to previous backup"
    echo "  status                      Show current install information"
    echo "  verify                      Run post-deploy verification"
    echo "  history                     Show upgrade/downgrade history"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  sudo bash $0 upgrade                  # latest from PyPI"
    echo "  sudo bash $0 upgrade 0.2.0            # specific version"
    echo "  sudo bash $0 upgrade --git            # from GitHub main"
    echo "  sudo bash $0 upgrade --git v0.2.0     # from GitHub tag v0.2.0"
    echo "  sudo bash $0 upgrade --git fix/dns    # from GitHub branch"
    echo "  sudo bash $0 downgrade 0.0.9          # rollback to old version"
    echo "  sudo bash $0 rollback                 # restore last backup"
    echo ""
    echo -e "${BOLD}Safety:${NC}"
    echo "  • Current version is backed up before every upgrade/downgrade"
    echo "  • Automatic rollback on failed health check after install"
    echo "  • Up to ${MAX_BACKUPS} backups retained (oldest auto-rotated)"
    echo "  • Full history logged to ${HISTORY_FILE}"
    echo ""
}

COMMAND="${1:-help}"
shift || true

case "${COMMAND}" in
    upgrade)    cmd_upgrade "$@" ;;
    downgrade)  cmd_downgrade "$@" ;;
    rollback)   cmd_rollback "$@" ;;
    status)     cmd_status "$@" ;;
    verify)     cmd_verify "$@" ;;
    history)    cmd_history "$@" ;;
    help|--help|-h)
        usage ;;
    *)
        error "Unknown command: ${COMMAND}"
        echo ""
        usage
        exit 1
        ;;
esac
