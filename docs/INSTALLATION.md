# Installation Guide

Complete installation guide for **dawos-agent** — PPP router management agent.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [One-Line Install](#one-line-install)
- [Install from Source](#install-from-source)
- [Non-Interactive Install](#non-interactive-install)
- [Manual Install](#manual-install)
- [Verify Installation](#verify-installation)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

---

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **OS** | Debian 11+ / Ubuntu 22.04+ | Other Linux distros may work but are untested |
| **Python** | 3.10+ | `python3-venv` module required |
| **Access** | Root / sudo | For system user, sudoers, systemd |
| **Disk** | 200 MB free in `/opt` | For virtualenv and dependencies |
| **Network** | curl or git | To download the source |

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

The installer downloads the source from GitHub, creates a system user, installs the package in a virtualenv, sets up systemd and sudoers, then starts the service.

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

- API key: randomly generated
- Listen: `0.0.0.0:8470`
- Log level: `info`
- Node name: system hostname
- accel-ppp paths: `/usr/bin/accel-cmd`, `/etc/accel-ppp.conf`

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

Or write it manually — see [systemd/dawos-agent.service](../systemd/dawos-agent.service) for the full unit file.

---

## Verify Installation

```bash
# service status
sudo systemctl status dawos-agent

# health check (no auth required)
curl -s http://localhost:8470/health | python3 -m json.tool

# authenticated call
curl -s -H 'X-API-Key: <your-key>' \
    http://localhost:8470/api/v1/system/info | python3 -m json.tool
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

---

## Troubleshooting

### Check logs

```bash
journalctl -u dawos-agent -n 50 --no-pager   # last 50 lines
journalctl -u dawos-agent -f                   # follow live
```

### Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError` | Broken venv | Reinstall: `sudo /opt/dawos-agent/venv/bin/pip install .` |
| `Address already in use` | Port conflict | `ss -tlnp \| grep 8470` — change `DAWOS_PORT` |
| `Permission denied` | Wrong ownership | `sudo chown -R dawos:dawos /opt/dawos-agent` |
| `sudo: a password is required` | Missing sudoers | Check: `sudo visudo -cf /etc/sudoers.d/dawos-agent` |
| `accel-cmd not found` | accel-ppp not installed | Install accel-ppp or update `ACCEL_CMD` path |

### Python too old

```bash
python3 --version   # need 3.10+

# Debian 12+ / Ubuntu 22.04+
sudo apt update && sudo apt install python3 python3-venv
```

---

## Security Notes

### API Key

- Always replace the default key before exposing the agent to any network
- Generate a strong key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- Use HTTPS (reverse proxy) in production — the key travels in an HTTP header

### File Permissions

| File | Mode | Owner | Why |
|------|------|-------|-----|
| `/etc/dawos-agent/agent.env` | `0640` | `root:dawos` | Contains API key |
| `/etc/sudoers.d/dawos-agent` | `0440` | `root:root` | Must be read-only |

### Sudoers

Only 6 specific commands are allowed via sudo — no shell, no wildcards, no unrestricted access. See [deploy/dawos-agent.sudoers](../deploy/dawos-agent.sudoers).

### Systemd Hardening

The service runs with `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`. Only explicitly listed paths are writable.

### Network

- Default: listens on `0.0.0.0:8470` (all interfaces)
- Production: bind to management interface only (`DAWOS_HOST=10.0.0.1`)
- TLS: put behind nginx/Caddy reverse proxy
