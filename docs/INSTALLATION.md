# Installation Guide

Complete installation guide for **dawos-agent** — the lightweight REST agent daemon for accel-ppp BNG nodes.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Install (Interactive)](#quick-install-interactive)
- [Automated Install (CI/Scripting)](#automated-install-ciscripting)
- [Manual Install (Step-by-Step)](#manual-install-step-by-step)
- [Verify Installation](#verify-installation)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

---

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **Operating System** | Debian 11+ / Ubuntu 22.04+ | Other Linux distros may work but are untested |
| **Python** | 3.10+ | `python3-venv` module required |
| **accel-ppp** | Installed and running | Agent manages it via `accel-cmd` CLI |
| **Access** | Root / sudo | Required for system user creation, sudoers, systemd |
| **Disk Space** | 200 MB free in `/opt` | For virtualenv and dependencies |

### Required System Tools

The agent invokes the following tools via `sudo` to manage BNG functions:

| Tool | Package | Used By |
|------|---------|---------|
| `nft` | nftables | NAT rules, firewall, diagnostics |
| `ip` | iproute2 | Network interfaces, NAT routing |
| `tc` | iproute2 | Traffic shaping / QoS |
| `ss` | iproute2 | Socket diagnostics |
| `vtysh` | frr | FRR routing daemon management |
| `sysctl` | procps | Kernel parameter tuning |
| `systemctl` | systemd | Service management |

---

## Quick Install (Interactive)

The bundled installer provides a guided, 6-phase installation with prompts for configuration:

```bash
git clone <repo-url>
cd dawos-agent
sudo bash install.sh
```

The installer will:

1. **Preflight check** — verify OS, Python version, disk space, and required tools
2. **Configuration wizard** — prompt for API key, listen address/port, node name, log level, and accel-ppp paths
3. **System setup** — create the `dawos` service user and required directories
4. **Package install** — create a Python virtualenv and install dawos-agent via pip
5. **Service & security** — install systemd unit, sudoers rules, enable and start the service
6. **Health check** — verify the agent is responding on the configured port

At the end of installation, the installer prints a summary with your API key, access URLs, and useful commands.

---

## Automated Install (CI/Scripting)

For unattended installations, use the `--yes` flag to accept all defaults without prompts:

```bash
sudo bash install.sh --yes
```

In non-interactive mode the installer will:

- Generate a secure random API key automatically
- Use all default settings (listen on `0.0.0.0:8470`, log level `info`)
- Use the system hostname as the node name
- Use default accel-ppp paths (`/usr/bin/accel-cmd`, `/etc/accel-ppp.conf`)

> **Important:** After automated install, retrieve the generated API key from the config file:
> ```bash
> sudo grep DAWOS_API_KEY /etc/dawos-agent/agent.env
> ```

---

## Manual Install (Step-by-Step)

If you prefer full control over the installation process, follow these steps.

### 1. Create the System User

Create a dedicated `dawos` system user with no login shell:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin \
    --home-dir /opt/dawos-agent dawos
```

Optionally add the user to the `systemd-journal` group for log access:

```bash
sudo usermod -aG systemd-journal dawos
```

### 2. Create Directories

```bash
sudo mkdir -p /opt/dawos-agent /etc/dawos-agent
sudo chown dawos:dawos /opt/dawos-agent
```

### 3. Create the Python Virtual Environment

```bash
sudo python3 -m venv /opt/dawos-agent/venv
sudo /opt/dawos-agent/venv/bin/pip install --upgrade pip
```

### 4. Install the Package

From the cloned repository root:

```bash
sudo /opt/dawos-agent/venv/bin/pip install .
```

Set ownership:

```bash
sudo chown -R dawos:dawos /opt/dawos-agent
```

### 5. Generate an API Key

Generate a cryptographically secure API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the output — you will need it in the next step and for client authentication.

### 6. Create the Configuration File

Create `/etc/dawos-agent/agent.env` with the following content:

```bash
sudo tee /etc/dawos-agent/agent.env > /dev/null << 'EOF'
# dawos-agent configuration

# API authentication — share this key with your management platform
DAWOS_API_KEY=<your-generated-api-key>

# Network binding
DAWOS_HOST=0.0.0.0
DAWOS_PORT=8470

# Node identity (appears in health checks and logs)
DAWOS_NODE_NAME=<your-node-hostname>

# accel-ppp integration
ACCEL_CMD=/usr/bin/accel-cmd
ACCEL_CLI_PORT=2001
ACCEL_CONFIG_PATH=/etc/accel-ppp.conf
ACCEL_SERVICE_NAME=accel-ppp

# Logging (debug | info | warning | error)
DAWOS_LOG_LEVEL=info
EOF
```

Set secure file permissions:

```bash
sudo chmod 0640 /etc/dawos-agent/agent.env
sudo chown root:dawos /etc/dawos-agent/agent.env
```

### 7. Install Sudoers Rules

Create the least-privilege sudoers file:

```bash
sudo tee /etc/sudoers.d/dawos-agent > /dev/null << 'EOF'
# dawos-agent — passwordless sudo for BNG management commands
dawos ALL=(ALL) NOPASSWD: /usr/sbin/nft
dawos ALL=(ALL) NOPASSWD: /usr/sbin/ip
dawos ALL=(ALL) NOPASSWD: /usr/sbin/tc
dawos ALL=(ALL) NOPASSWD: /usr/bin/vtysh
dawos ALL=(ALL) NOPASSWD: /usr/sbin/sysctl
dawos ALL=(ALL) NOPASSWD: /usr/bin/tee
EOF
```

Set permissions and validate syntax:

```bash
sudo chmod 0440 /etc/sudoers.d/dawos-agent
sudo visudo -cf /etc/sudoers.d/dawos-agent
```

### 8. Install the Systemd Unit

```bash
sudo tee /etc/systemd/system/dawos-agent.service > /dev/null << 'EOF'
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

# Security hardening
NoNewPrivileges=false
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/etc/accel-ppp.conf /etc/accel-ppp.d /etc/accel-nat-egress.nft /etc/sysctl.d /etc/nftables.conf
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dawos-agent

[Install]
WantedBy=multi-user.target
EOF
```

### 9. Enable and Start the Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable dawos-agent
sudo systemctl start dawos-agent
```

---

## Verify Installation

### Check Service Status

```bash
sudo systemctl status dawos-agent
```

Expected output should show `Active: active (running)`.

### Health Check (Unauthenticated)

The `/health` endpoint is public and requires no API key:

```bash
curl -s http://localhost:8470/health | python3 -m json.tool
```

Expected response:

```json
{
    "status": "ok",
    "version": "0.1.0",
    "node_name": "your-hostname"
}
```

### Authenticated API Call

Test an authenticated endpoint using your API key:

```bash
curl -s -H 'X-API-Key: <your-api-key>' \
    http://localhost:8470/api/v1/system/info | python3 -m json.tool
```

### Interactive API Documentation

The agent ships with built-in API docs accessible in a browser:

| URL | Interface |
|-----|-----------|
| `http://<host>:8470/docs` | Swagger UI (interactive) |
| `http://<host>:8470/redoc` | ReDoc (read-only) |

---

## Upgrading

### Using the Installer (Recommended)

The installer automatically detects an existing installation and runs in **upgrade mode**, which preserves your configuration:

```bash
cd dawos-agent
git pull
sudo bash install.sh
```

In upgrade mode:

- Your `/etc/dawos-agent/agent.env` is **not overwritten**
- The Python package is reinstalled with updated code
- The systemd unit and sudoers files are refreshed
- The service is restarted automatically

### Manual Upgrade

```bash
cd dawos-agent
git pull
sudo /opt/dawos-agent/venv/bin/pip install .
sudo chown -R dawos:dawos /opt/dawos-agent
sudo systemctl restart dawos-agent
```

After upgrading, verify the new version:

```bash
curl -s http://localhost:8470/health | python3 -m json.tool
```

---

## Uninstalling

### Using the Installer

```bash
sudo bash install.sh --uninstall
```

The uninstaller will:

1. Stop and disable the systemd service
2. Remove the systemd unit file
3. Remove the sudoers file
4. Remove the installation directory (`/opt/dawos-agent`)
5. Optionally remove configuration (`/etc/dawos-agent`)
6. Optionally remove the `dawos` system user

### Manual Uninstall

```bash
# Stop and disable the service
sudo systemctl stop dawos-agent
sudo systemctl disable dawos-agent

# Remove systemd unit
sudo rm /etc/systemd/system/dawos-agent.service
sudo systemctl daemon-reload

# Remove sudoers
sudo rm /etc/sudoers.d/dawos-agent

# Remove installation
sudo rm -rf /opt/dawos-agent

# Remove configuration (optional — keep if you plan to reinstall)
sudo rm -rf /etc/dawos-agent

# Remove system user (optional)
sudo userdel dawos
```

---

## Troubleshooting

### Service Won't Start

Check the journal for error messages:

```bash
journalctl -u dawos-agent -n 50 --no-pager
```

Common causes:

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError` | Broken virtualenv | Reinstall: `sudo /opt/dawos-agent/venv/bin/pip install .` |
| `Address already in use` | Port 8470 conflict | Check: `ss -tlnp \| grep 8470` and change `DAWOS_PORT` |
| `Permission denied` | Wrong file ownership | `sudo chown -R dawos:dawos /opt/dawos-agent` |
| `FileNotFoundError: accel-cmd` | accel-ppp not installed | Install accel-ppp or update `ACCEL_CMD` path in `agent.env` |

### Permission Denied Errors at Runtime

If the agent logs `sudo: a password is required` or similar:

1. Verify the sudoers file is installed and valid:
   ```bash
   sudo visudo -cf /etc/sudoers.d/dawos-agent
   ```
2. Verify the service runs as the `dawos` user:
   ```bash
   ps aux | grep dawos-agent
   ```
3. Verify the `dawos` user exists:
   ```bash
   id dawos
   ```

### Port Already in Use

```bash
ss -tlnp | grep 8470
```

Either stop the conflicting process or change the port in `/etc/dawos-agent/agent.env`:

```
DAWOS_PORT=8471
```

Then restart:

```bash
sudo systemctl restart dawos-agent
```

### accel-cmd Not Found

Verify the `accel-cmd` binary exists at the configured path:

```bash
ls -la /usr/bin/accel-cmd
```

If installed elsewhere, update `/etc/dawos-agent/agent.env`:

```
ACCEL_CMD=/path/to/accel-cmd
```

### Python Version Too Old

```bash
python3 --version
```

If below 3.10, install a newer version:

```bash
# Debian 12+ / Ubuntu 22.04+
sudo apt update && sudo apt install python3 python3-venv

# For older systems, use the deadsnakes PPA (Ubuntu)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update && sudo apt install python3.11 python3.11-venv
```

### Checking Logs in Real Time

```bash
journalctl -u dawos-agent -f
```

---

## Security Notes

### API Key

- **Always replace the default API key** before exposing the agent to any network.
- Generate a strong key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- The API key is transmitted via the `X-API-Key` HTTP header. Use HTTPS (via reverse proxy) in production to protect it in transit.

### File Permissions

| File | Permissions | Owner | Purpose |
|------|-------------|-------|---------|
| `/etc/dawos-agent/agent.env` | `0640` | `root:dawos` | Contains the API key — readable by root and the service user only |
| `/etc/sudoers.d/dawos-agent` | `0440` | `root:root` | Sudoers rules — must be read-only |

### Sudoers: Least Privilege

The sudoers file grants passwordless `sudo` access **only** to the specific commands the agent needs:

- `nft` — manage nftables firewall and NAT rules
- `ip` — manage network interfaces and routes
- `tc` — manage traffic shaping / QoS policies
- `vtysh` — interact with the FRR routing daemon
- `sysctl` — read and tune kernel parameters
- `tee` — write configuration files to protected paths

No shell access, no wildcard commands, no unrestricted `sudo`.

### Systemd Hardening

The systemd unit includes several security directives:

| Directive | Effect |
|-----------|--------|
| `ProtectSystem=strict` | Mounts the entire filesystem read-only except explicitly listed paths |
| `ProtectHome=true` | Makes `/home`, `/root`, and `/run/user` inaccessible |
| `PrivateTmp=true` | Gives the service its own isolated `/tmp` directory |
| `ReadWritePaths=...` | Whitelists only the specific config files the agent needs to modify |

### Network Exposure

- By default, the agent listens on `0.0.0.0:8470` (all interfaces).
- In production, consider binding to a management interface only (e.g., `DAWOS_HOST=10.0.0.1`).
- If the agent is accessed remotely, place it behind a TLS-terminating reverse proxy (nginx, Caddy) rather than exposing the HTTP port directly.
