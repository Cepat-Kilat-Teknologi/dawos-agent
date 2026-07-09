# Installation Guide

Complete installation guide for **DawOS Agent** -- open-source broadband network gateway management daemon.

---

## Table of Contents

- [Hardware Requirements](#hardware-requirements)
- [Software Prerequisites](#software-prerequisites)
- [One-Line Install](#one-line-install)
- [Install from Source](#install-from-source)
- [Non-Interactive Install](#non-interactive-install)
- [What the Installer Does](#what-the-installer-does)
- [Manual Install](#manual-install)
- [Verify Installation](#verify-installation)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

---

## Hardware Requirements

### Minimum

| Resource | Minimum | Notes |
|----------|---------|-------|
| **CPU** | 1 vCPU (x86_64) | ARM is not supported |
| **RAM** | 512 MB | Agent uses ~60 MB RSS, accel-ppp uses ~5 MB RSS at idle |
| **Disk** | 2 GB free | 55 MB for agent venv, ~500 MB for build dependencies if compiling accel-ppp from source |
| **Network** | 1 NIC | Minimum for management access |

### Recommended for Production

| Resource | Recommended | Notes |
|----------|-------------|-------|
| **CPU** | 2+ vCPU | accel-ppp needs CPU headroom for PPP session handling |
| **RAM** | 1 GB+ | Scale with number of concurrent PPPoE sessions |
| **Disk** | 5 GB+ | Room for logs, config backups, and OS updates |
| **Network** | 2+ NICs | Separate management and subscriber-facing interfaces |

### Measured Resource Usage

| Component | Memory (RSS) | Disk | CPU at Idle |
|-----------|:------------:|:----:|:-----------:|
| dawos-agent (Uvicorn + FastAPI) | ~60 MB | 55 MB | <1% |
| accel-ppp daemon (0 sessions) | ~5 MB | ~2 MB | <1% |
| Build dependencies (cmake, gcc, g++, libssl-dev) | — | ~500 MB | — |

> **Scaling note:** These measurements are for the agent with zero PPPoE sessions. A production BNG serving thousands of subscribers needs significantly more RAM and CPU for accel-ppp. Consult the [accel-ppp documentation](https://accel-ppp.readthedocs.io/) for BNG sizing.

---

## Software Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **OS** | Debian 11+ / Ubuntu 22.04+ | Other Linux distros may work but are untested |
| **Python** | 3.9+ | `python3-venv` module required |
| **Access** | Root / sudo | For system user, sudoers, systemd |
| **Network** | curl or git | To download the source |

### accel-ppp

The installer automatically detects whether accel-ppp is installed:

- **Found:** Skips build, creates config and systemd unit if missing
- **Not found:** Builds from source (~2–5 minutes on 2 vCPU)

Build dependencies installed automatically:

```
cmake gcc g++ make git libssl-dev libpcre3-dev liblua5.1-0-dev
```

### System Tools

The agent uses `sudo` to call these tools for router management:

| Tool | Package | Purpose |
|------|---------|---------|
| `nft` | nftables | Firewall and NAT rules |
| `ip` | iproute2 | Network interfaces and routes |
| `tc` | iproute2 | Traffic shaping / QoS |
| `vtysh` | frr | FRR routing daemon (BGP, OSPF, RIP) |
| `sysctl` | procps | Kernel parameter tuning |
| `tee` | coreutils | Config file writes |

These are optional — the agent installs and runs without them, but related endpoints will return errors.

---

## One-Line Install

```bash
curl -sL https://raw.githubusercontent.com/Cepat-Kilat-Teknologi/dawos-agent/main/install.sh | sudo bash
```

The installer downloads the source from GitHub, builds accel-ppp if needed, creates a system user, installs the package in a virtualenv, sets up systemd and sudoers, then starts the service.

For non-interactive (accepts all defaults):

```bash
curl -sL https://raw.githubusercontent.com/Cepat-Kilat-Teknologi/dawos-agent/main/install.sh | sudo bash -s -- --yes
```

> After install, get your API key:
> ```bash
> sudo grep DAWOS_API_KEY /etc/dawos-agent/agent.env
> ```

---

## Install from Source

```bash
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
sudo bash install.sh
```

The installer detects local source and skips the download step.

---

## Non-Interactive Install

Use `--yes` to skip all prompts (good for automation/CI):

```bash
sudo bash install.sh --yes
```

Defaults:

- API key: randomly generated (43 characters, URL-safe base64)
- Listen: `0.0.0.0:8470`
- Log level: `info`
- Node name: system hostname
- accel-ppp paths: `/usr/bin/accel-cmd`, `/etc/accel-ppp.conf`

---

## What the Installer Does

The installer (`install.sh` v2.0) performs these steps in order:

| Step | Description |
|------|-------------|
| **1. Preflight** | Checks OS, Python, disk space, required tools |
| **2. Configure** | Prompts for API key, listen address, node name (or uses defaults with `--yes`) |
| **3. System setup** | Creates `dawos` system user, adds to `systemd-journal` group, creates directories |
| **4. accel-ppp** | Detects or builds accel-ppp from source, writes `/etc/accel-ppp.conf`, creates systemd unit |
| **5. Download** | Downloads dawos-agent source from GitHub (skipped if running from cloned repo) |
| **6. Install** | Creates Python venv, installs package with pip |
| **7. Permissions** | Sets ownership of `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/` to the `dawos` user (required for config checkpoint/rollback) |
| **8. Service** | Installs sudoers rules, systemd unit with security hardening (`Restart=always`, `WatchdogSec=30`), enables and starts service |
| **9. Verify** | Runs health check to confirm the agent is responding |

### accel-ppp Configuration

The installer creates a starter `/etc/accel-ppp.conf` with:

- PPPoE listener (disabled by default — edit interface name)
- Local IP pool (`10.0.0.1/24`)
- DNS servers (`8.8.8.8`, `8.8.4.4`)
- TCP CLI on port 2001 (required for `accel-cmd`)
- Log file at `/var/log/accel-ppp/accel-ppp.log`
- pppd-compat hooks for event integration

> **Important:** The config uses `tcp=` mode for the `[cli]` section, NOT `telnet=`. This is required for `accel-cmd` to connect.

---

## Manual Install

If you want full control, do it step by step.

### 1. Create system user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin \
    --home-dir /opt/dawos-agent dawos
sudo usermod -aG systemd-journal dawos
```

### 2. Create directories

```bash
sudo mkdir -p /opt/dawos-agent /etc/dawos-agent
sudo chown dawos:dawos /opt/dawos-agent
```

### 3. Install the package

```bash
sudo python3 -m venv /opt/dawos-agent/venv
sudo /opt/dawos-agent/venv/bin/pip install --upgrade pip

# from cloned repo or downloaded source
sudo /opt/dawos-agent/venv/bin/pip install .
sudo chown -R dawos:dawos /opt/dawos-agent
```

### 4. Generate an API key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5. Create config file

```bash
sudo tee /etc/dawos-agent/agent.env > /dev/null << 'EOF'
DAWOS_API_KEY=<your-generated-key>
DAWOS_HOST=0.0.0.0
DAWOS_PORT=8470
DAWOS_NODE_NAME=<your-hostname>
DAWOS_LOG_LEVEL=info
ACCEL_CMD=/usr/bin/accel-cmd
ACCEL_CLI_PORT=2001
ACCEL_CONFIG_PATH=/etc/accel-ppp.conf
ACCEL_SERVICE_NAME=accel-ppp
EOF

sudo chmod 0640 /etc/dawos-agent/agent.env
sudo chown root:dawos /etc/dawos-agent/agent.env
```

### 6. Install sudoers

```bash
sudo tee /etc/sudoers.d/dawos-agent > /dev/null << 'EOF'
# dawos-agent — passwordless sudo for router management
dawos ALL=(ALL) NOPASSWD: /usr/sbin/nft
dawos ALL=(ALL) NOPASSWD: /usr/sbin/ip
dawos ALL=(ALL) NOPASSWD: /usr/sbin/tc
dawos ALL=(ALL) NOPASSWD: /usr/bin/vtysh
dawos ALL=(ALL) NOPASSWD: /usr/sbin/sysctl
dawos ALL=(ALL) NOPASSWD: /usr/bin/tee
EOF

sudo chmod 0440 /etc/sudoers.d/dawos-agent
sudo visudo -cf /etc/sudoers.d/dawos-agent
```

### 7. Install systemd unit

```bash
sudo cp systemd/dawos-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dawos-agent
```

Or write it manually — see [systemd/dawos-agent.service](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/systemd/dawos-agent.service) for the full unit file.

---

## Verify Installation

```bash
# service status
sudo systemctl status dawos-agent
sudo systemctl status accel-ppp

# health check (no auth required)
curl -s http://localhost:8470/health | python3 -m json.tool

# authenticated call
curl -s -H 'X-API-Key: <your-key>' \
    http://localhost:8470/api/v1/system/info | python3 -m json.tool

# accel-cmd direct test
accel-cmd show version
```

API docs are available at:

- `http://<host>:8470/docs` — Swagger UI
- `http://<host>:8470/redoc` — ReDoc

---

## Upgrading

### With installer (recommended)

The installer detects existing installs and preserves config:

```bash
cd dawos-agent
git pull
sudo bash install.sh
```

### Manual

```bash
cd dawos-agent
git pull
sudo /opt/dawos-agent/venv/bin/pip install .
sudo chown -R dawos:dawos /opt/dawos-agent
sudo systemctl restart dawos-agent
```

Check the new version:

```bash
curl -s http://localhost:8470/health | python3 -m json.tool
```

---

## Uninstalling

### With installer

```bash
sudo bash install.sh --uninstall
```

This removes the dawos-agent service, user, directories, and sudoers. It does **not** remove accel-ppp or its configuration.

### Manual

```bash
sudo systemctl stop dawos-agent
sudo systemctl disable dawos-agent
sudo rm /etc/systemd/system/dawos-agent.service
sudo systemctl daemon-reload
sudo rm /etc/sudoers.d/dawos-agent
sudo rm -rf /opt/dawos-agent
sudo rm -rf /etc/dawos-agent     # optional — keeps config if you plan to reinstall
sudo userdel dawos               # optional
```

### Full cleanup (including accel-ppp)

```bash
sudo systemctl stop accel-ppp
sudo systemctl disable accel-ppp
sudo rm /etc/systemd/system/accel-ppp.service
sudo rm /etc/accel-ppp.conf
sudo rm -rf /etc/accel-ppp.d
sudo rm -rf /var/log/accel-ppp
sudo rm -f /usr/sbin/accel-pppd /usr/bin/accel-cmd
sudo systemctl daemon-reload
```

---

## Troubleshooting

### Check logs

```bash
journalctl -u dawos-agent -n 50 --no-pager   # last 50 lines
journalctl -u dawos-agent -f                   # follow live
journalctl -u accel-ppp -n 20 --no-pager      # accel-ppp logs
```

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError` | Broken venv | Reinstall: `sudo /opt/dawos-agent/venv/bin/pip install .` |
| `Address already in use` | Port conflict | `ss -tlnp \| grep 8470` — change `DAWOS_PORT` |
| `Permission denied` | Wrong ownership | `sudo chown -R dawos:dawos /opt/dawos-agent` |
| `sudo: a password is required` | Missing sudoers | Check: `sudo visudo -cf /etc/sudoers.d/dawos-agent` |
| `accel-cmd not found` | accel-ppp not installed | Reinstall with `install.sh` to build from source |
| `Connection to localhost:2001 failed` | accel-ppp not running | `sudo systemctl start accel-ppp` |
| `pppd_compat: ... No such file` | Inline comments in config | Ensure no `#` comments on value lines in `/etc/accel-ppp.conf` |
| `failed to load vlan_mon module` | Normal in VMs | Harmless warning — vlan_mon requires physical NICs |

### Python version

```bash
python3 --version   # need 3.9+

# Debian 12+ / Ubuntu 22.04+
sudo apt update && sudo apt install python3 python3-venv
```

---

## Security Notes

### API Key

- The installer generates a strong 43-character URL-safe key automatically
- Generate a custom key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- Use HTTPS (reverse proxy) in production — the key travels in an HTTP header

### File Permissions

| File | Mode | Owner | Why |
|------|------|-------|-----|
| `/etc/dawos-agent/agent.env` | `0640` | `root:dawos` | Contains API key |
| `/etc/sudoers.d/dawos-agent` | `0440` | `root:root` | Must be read-only |

### Sudoers

Only 6 specific commands are allowed via sudo — no shell, no wildcards, no unrestricted access. See [deploy/dawos-agent.sudoers](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/deploy/dawos-agent.sudoers).

### accel-ppp Config Ownership

The installer automatically sets ownership of `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/` to the `dawos` user. This is required for config checkpoint and rollback to work.

If you install manually, set this ownership yourself:

```bash
sudo chown dawos:dawos /etc/accel-ppp.conf
sudo chown -R dawos:dawos /etc/accel-ppp.d/
```

Without correct ownership, config backup operations fail with HTTP 500.

### Systemd Hardening

The service runs with `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `WatchdogSec=30`, and `Restart=always`. Only explicitly listed paths are writable. See the [Security documentation](../development/security.md) for the full list of directives.

### Network

- Default: listens on `0.0.0.0:8470` (all interfaces)
- Production: bind to management interface only (`DAWOS_HOST=10.0.0.1`)
- TLS: put behind nginx/Caddy reverse proxy
