# Configuration Reference

Complete configuration reference for **dawos-agent** — PPP router management agent.

---

## Table of Contents

- [Configuration Methods](#configuration-methods)
- [Settings Reference](#settings-reference)
- [File Locations](#file-locations)
- [Sudoers Reference](#sudoers-reference)
- [Systemd Unit Configuration](#systemd-unit-configuration)
- [Logging](#logging)
- [Network and Firewall](#network-and-firewall)
- [Production Recommendations](#production-recommendations)

---

## Configuration Methods

dawos-agent uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for configuration. Settings are resolved in the following order of precedence (highest to lowest):

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | **Environment variables** | `export DAWOS_PORT=9090` |
| 2 | **`/etc/dawos-agent/agent.env`** | Loaded by the systemd `EnvironmentFile` directive |
| 3 (lowest) | **`.env` file** in the working directory | For development / manual runs |

All environment variables use the `DAWOS_` prefix. For example, the `port` setting maps to `DAWOS_PORT`.

> **Note:** The `ACCEL_CMD`, `ACCEL_CLI_PORT`, `ACCEL_CONFIG_PATH`, and `ACCEL_SERVICE_NAME` variables are exceptions — they do **not** use the `DAWOS_` prefix (they use the `DAWOS_` prefix internally via pydantic-settings, but can also be set directly for compatibility).

### Editing the Configuration

```bash
# Edit the main config file
sudo nano /etc/dawos-agent/agent.env

# Restart to apply changes
sudo systemctl restart dawos-agent
```

### Overriding via Environment

You can override any setting by exporting the environment variable before starting the service, or by adding it to the `[Service]` section of the systemd unit:

```ini
[Service]
Environment=DAWOS_LOG_LEVEL=debug
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart dawos-agent
```

---

## Settings Reference

### Agent Identity

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `DAWOS_NODE_NAME` | System hostname | `string` | Human-readable identifier for this BNG node. Included in health-check responses to help operators identify which node answered. |

### Network

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `DAWOS_HOST` | `0.0.0.0` | `string` | IP address to bind the HTTP listener on. `0.0.0.0` listens on all interfaces. Set to a specific IP to restrict access. |
| `DAWOS_PORT` | `8470` | `integer` | TCP port for the HTTP listener. Chosen to avoid conflicts with accel-ppp CLI (2001) and common web server ports. |

### Authentication

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `DAWOS_API_KEY` | `changeme-generate-a-strong-key` | `string` | Shared secret for `X-API-Key` header authentication. **Must be replaced in production.** All API endpoints except `/health` require this key. |

### accel-ppp Integration

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `DAWOS_ACCEL_CMD` | `/usr/bin/accel-cmd` | `string` | Absolute path to the `accel-cmd` CLI binary used to communicate with the running accel-ppp daemon. |
| `DAWOS_ACCEL_CLI_PORT` | `2001` | `integer` | TCP port that the accel-ppp CLI telnet interface listens on (used by `accel-cmd`). |
| `DAWOS_ACCEL_CONFIG_PATH` | `/etc/accel-ppp.conf` | `string` | Filesystem path to the main accel-ppp configuration file. The agent reads and modifies this file for config management operations. |
| `DAWOS_ACCEL_SERVICE_NAME` | `accel-ppp` | `string` | Systemd service unit name for accel-ppp. Used when starting, stopping, or restarting the daemon via `systemctl`. |

### Logging

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `DAWOS_LOG_LEVEL` | `info` | `string` | Uvicorn / Python log level. Valid values: `debug`, `info`, `warning`, `error`. |

### Example Configuration File

```bash
# /etc/dawos-agent/agent.env

# API authentication
DAWOS_API_KEY=dGhpcyBpcyBhIHNlY3VyZSBrZXkgZXhhbXBsZQ

# Network binding
DAWOS_HOST=0.0.0.0
DAWOS_PORT=8470

# Node identity
DAWOS_NODE_NAME=bng-jakarta-01

# accel-ppp integration
DAWOS_ACCEL_CMD=/usr/bin/accel-cmd
DAWOS_ACCEL_CLI_PORT=2001
DAWOS_ACCEL_CONFIG_PATH=/etc/accel-ppp.conf
DAWOS_ACCEL_SERVICE_NAME=accel-ppp

# Logging
DAWOS_LOG_LEVEL=info
```

---

## File Locations

| Path | Purpose | Owner | Permissions |
|------|---------|-------|-------------|
| `/opt/dawos-agent/` | Installation root directory | `dawos:dawos` | `0755` |
| `/opt/dawos-agent/venv/` | Python virtual environment (interpreter, dependencies) | `dawos:dawos` | `0755` |
| `/opt/dawos-agent/venv/bin/dawos-agent` | Agent executable (console script entry point) | `dawos:dawos` | `0755` |
| `/etc/dawos-agent/` | Configuration directory | `root:dawos` | `0750` |
| `/etc/dawos-agent/agent.env` | Main configuration file (contains API key) | `root:dawos` | `0640` |
| `/etc/systemd/system/dawos-agent.service` | Systemd service unit file | `root:root` | `0644` |
| `/etc/sudoers.d/dawos-agent` | Sudo rules for the `dawos` user | `root:root` | `0440` |

### Runtime Paths

The agent reads and writes these paths during normal operation (whitelisted in the systemd unit via `ReadWritePaths`):

| Path | Purpose |
|------|---------|
| `/etc/accel-ppp.conf` | Main accel-ppp configuration file |
| `/etc/accel-ppp.d/` | Backup directory for config checkpoints |
| `/etc/accel-nat-egress.nft` | NAT egress nftables rules |
| `/etc/sysctl.d/` | Kernel parameter configuration files |
| `/etc/nftables.conf` | Main nftables configuration |

---

## Sudoers Reference

The sudoers file at `/etc/sudoers.d/dawos-agent` grants the `dawos` user passwordless `sudo` access to a minimal set of commands. Each command is listed below with the service modules that use it.

### nftables — `/usr/sbin/nft`

```
dawos ALL=(ALL) NOPASSWD: /usr/sbin/nft
```

**Used by:** `nat.py`, `firewall.py`, `diagnostics.py`

Manages nftables rules for:
- NAT masquerade and SNAT/DNAT rules
- Firewall rule creation, deletion, and listing
- Diagnostic queries (listing rulesets, counters)

### iproute2 — `/usr/sbin/ip`

```
dawos ALL=(ALL) NOPASSWD: /usr/sbin/ip
```

**Used by:** `nat.py`, `network.py`

Manages network configuration for:
- Interface address assignment and status changes
- Route table management for NAT and policy routing
- Network diagnostics (link state, neighbor table)

### Traffic Control — `/usr/sbin/tc`

```
dawos ALL=(ALL) NOPASSWD: /usr/sbin/tc
```

**Used by:** `traffic.py`

Manages traffic shaping for:
- HTB/TBF queueing disciplines for subscriber bandwidth
- Traffic class creation and rate limiting
- Shaper statistics and diagnostics

### FRR Routing — `/usr/bin/vtysh`

```
dawos ALL=(ALL) NOPASSWD: /usr/bin/vtysh
```

**Used by:** `routing.py`

Interacts with the FRR routing daemon for:
- BGP / OSPF / static route management
- Routing table inspection
- Running configuration display

### Kernel Parameters — `/usr/sbin/sysctl`

```
dawos ALL=(ALL) NOPASSWD: /usr/sbin/sysctl
```

**Used by:** `firewall.py`, `diagnostics.py`

Manages kernel tunables for:
- IP forwarding (`net.ipv4.ip_forward`)
- Conntrack tuning
- Network stack diagnostics

### File Writer — `/usr/bin/tee`

```
dawos ALL=(ALL) NOPASSWD: /usr/bin/tee
```

**Used by:** `firewall.py`, `nat.py`, `diagnostics.py`

Writes configuration files to paths owned by root:
- nftables rule files
- sysctl configuration snippets
- NAT egress configuration

---

## Systemd Unit Configuration

The service unit at `/etc/systemd/system/dawos-agent.service` controls how the agent runs. Each directive is explained below.

### [Unit] Section

| Directive | Value | Purpose |
|-----------|-------|---------|
| `Description` | `dawos-agent — PPP router management daemon` | Human-readable service description shown in `systemctl status` |
| `Documentation` | `https://github.com/...` | Link to project documentation |
| `After` | `network-online.target accel-ppp.service` | Delays startup until networking is ready and accel-ppp has started |
| `Wants` | `network-online.target` | Soft dependency — request network but don't fail if unavailable |

### [Service] Section

| Directive | Value | Purpose |
|-----------|-------|---------|
| `Type` | `simple` | The process started by `ExecStart` is the main service process |
| `User` | `dawos` | Run the agent as the unprivileged `dawos` system user |
| `Group` | `dawos` | Primary group for file access |
| `EnvironmentFile` | `-/etc/dawos-agent/agent.env` | Load configuration from this file. The `-` prefix means "don't fail if the file is missing" |
| `ExecStart` | `/opt/dawos-agent/venv/bin/dawos-agent` | Command to start the agent (Uvicorn ASGI server) |
| `Restart` | `on-failure` | Automatically restart the agent if it exits with a non-zero code |
| `RestartSec` | `5` | Wait 5 seconds between restart attempts |
| `StartLimitBurst` | `3` | Allow at most 3 restart attempts... |
| `StartLimitIntervalSec` | `60` | ...within a 60-second window. Prevents crash-loop storms |

### Security Hardening Directives

| Directive | Value | Purpose |
|-----------|-------|---------|
| `NoNewPrivileges` | `false` | Set to `false` because the agent needs `sudo` to escalate privileges for system commands. Setting `true` would break sudoers rules |
| `ProtectSystem` | `strict` | Mounts the entire filesystem read-only except paths listed in `ReadWritePaths`. Prevents accidental writes to system files |
| `ProtectHome` | `true` | Makes `/home`, `/root`, and `/run/user` completely inaccessible to the service |
| `ReadWritePaths` | `/etc/accel-ppp.conf /etc/accel-ppp.d ...` | Explicitly whitelists the config files the agent needs to modify |
| `PrivateTmp` | `true` | Gives the service its own isolated `/tmp` directory, invisible to other processes |

### Logging Directives

| Directive | Value | Purpose |
|-----------|-------|---------|
| `StandardOutput` | `journal` | Route stdout to the systemd journal |
| `StandardError` | `journal` | Route stderr to the systemd journal |
| `SyslogIdentifier` | `dawos-agent` | Tag all journal entries with `dawos-agent` for easy filtering |

### [Install] Section

| Directive | Value | Purpose |
|-----------|-------|---------|
| `WantedBy` | `multi-user.target` | Start the service automatically on normal (non-graphical) boot |

---

## Logging

### Log Destination

All log output is sent to the **systemd journal** via stdout/stderr. No log files are written to disk by the agent itself.

### Viewing Logs

```bash
# Follow logs in real time
journalctl -u dawos-agent -f

# View the last 50 log entries
journalctl -u dawos-agent -n 50

# View logs since the last boot
journalctl -u dawos-agent -b

# View logs from a specific time range
journalctl -u dawos-agent --since "2024-01-01 10:00:00" --until "2024-01-01 11:00:00"

# View only errors
journalctl -u dawos-agent -p err

# Export logs as JSON
journalctl -u dawos-agent -o json --no-pager
```

### Log Levels

Set via `DAWOS_LOG_LEVEL` in the configuration file:

| Level | Description | Recommended For |
|-------|-------------|-----------------|
| `debug` | Verbose output including request/response details | Development, troubleshooting |
| `info` | Normal operational messages (startup, requests) | Default for staging |
| `warning` | Potential issues that don't prevent operation | Production (recommended) |
| `error` | Errors that affect functionality | Quiet production environments |

### Access Logs

The agent runs on Uvicorn with `access_log=True`, so every HTTP request is logged with method, path, status code, and response time. These appear in the journal alongside application logs.

### Syslog Identifier

All journal entries are tagged with `SyslogIdentifier=dawos-agent`, allowing you to filter exclusively for agent logs even when other services share the same journal.

---

## Network and Firewall

### Default Listening Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Address | `0.0.0.0` | All interfaces |
| Port | `8470` | Avoids conflicts with accel-ppp CLI (2001) and web servers (80/443) |
| Protocol | HTTP/1.1 | Plain HTTP — use a reverse proxy for TLS |

### Firewall Rules

If the host runs `nftables` or `iptables`, allow inbound access on the agent port:

```bash
# nftables
sudo nft add rule inet filter input tcp dport 8470 accept

# iptables (legacy)
sudo iptables -A INPUT -p tcp --dport 8470 -j ACCEPT
```

To restrict access to a management subnet:

```bash
# nftables — allow only 10.0.0.0/24
sudo nft add rule inet filter input ip saddr 10.0.0.0/24 tcp dport 8470 accept

# iptables
sudo iptables -A INPUT -p tcp -s 10.0.0.0/24 --dport 8470 -j ACCEPT
```

### Running Behind a Reverse Proxy

For TLS termination and additional security, place the agent behind nginx or Caddy:

**nginx example:**

```nginx
server {
    listen 443 ssl;
    server_name bng-agent.example.com;

    ssl_certificate     /etc/ssl/certs/bng-agent.pem;
    ssl_certificate_key /etc/ssl/private/bng-agent.key;

    location / {
        proxy_pass http://127.0.0.1:8470;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

When using a reverse proxy, bind the agent to localhost only:

```
DAWOS_HOST=127.0.0.1
```

---

## Production Recommendations

### Security

1. **Generate a strong API key** — never use the default value:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Restrict the listen address** if the agent only serves local or management-network traffic:
   ```
   DAWOS_HOST=10.0.0.1
   ```

3. **Use TLS** — deploy a reverse proxy (nginx, Caddy) in front of the agent for HTTPS.

4. **Rotate API keys** periodically. Update `/etc/dawos-agent/agent.env` and restart the service.

### Logging

5. **Set log level to `warning`** in production to reduce journal volume:
   ```
   DAWOS_LOG_LEVEL=warning
   ```

6. **Configure log rotation** — systemd journal handles this automatically via `/etc/systemd/journald.conf`. Set `SystemMaxUse` to control disk usage.

### Monitoring

7. **Monitor the `/health` endpoint** — it is unauthenticated and returns the agent version, node name, and status. Use it as a health check target in your monitoring system (Prometheus blackbox exporter, Uptime Kuma, etc.):
   ```bash
   curl -sf http://localhost:8470/health
   ```

8. **Set up alerting** on systemd service failures:
   ```bash
   # Check if the service is active
   systemctl is-active dawos-agent
   ```

### Backup

9. **Back up the configuration file** — it contains your API key and node-specific settings:
   ```bash
   cp /etc/dawos-agent/agent.env /etc/dawos-agent/agent.env.bak
   ```

10. **Include in your infrastructure-as-code** — the `agent.env` file is the only node-specific state. Everything else can be reinstalled from the repository.

### Resource Usage

The agent is lightweight by design:

- **Memory:** ~60 MB RSS (Python + Uvicorn + FastAPI)
- **CPU:** Near zero at idle; brief spikes during API calls that invoke system commands
- **Disk:** ~55 MB for the virtualenv and dependencies
- **Network:** Only active when serving API requests — no background polling or outbound connections

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| **CPU** | 1 vCPU (x86_64) | 2+ vCPU |
| **RAM** | 512 MB | 1 GB+ |
| **Disk** | 2 GB free | 5 GB+ |
| **OS** | Debian 11+ / Ubuntu 22.04+ | Ubuntu 24.04 LTS |

See [Installation](installation.md) for detailed hardware sizing guidance.
