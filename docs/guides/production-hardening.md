# Production Hardening

Recommendations for running DawOS Agent reliably in production environments. This guide covers resource planning, log management, memory safety, process supervision, scaling, and operational best practices.

---

## Resource Planning

### Measured Footprint

These numbers are measured from a live deployment on a 2 vCPU / 2 GB RAM / 12 GB disk virtual machine running Ubuntu 22.04:

| Component | Memory (RSS) | CPU (idle) | CPU (under load) |
|-----------|:------------:|:----------:|:-----------------:|
| dawos-agent (FastAPI + Uvicorn) | 64 MB | < 0.1% | < 2% |
| accel-ppp daemon (0 sessions) | 6 MB | 0% | varies |
| Combined management stack | **70 MB** | **< 0.2%** | **< 3%** |

The 151 API endpoints are function registrations, not running processes. At runtime, only the endpoint being called executes. Each request spawns a single lightweight subprocess (`accel-cmd`, `nft`, `ip`, etc.), collects the output, and returns JSON. The entire cycle typically completes in under 100 milliseconds.

### Sizing by Scale

| Scale | Sessions | CPU | RAM | Disk | Notes |
|-------|:--------:|:---:|:---:|:----:|-------|
| Small | < 500 | 2 vCPU | 2 GB | 10 GB | Sufficient for most deployments |
| Medium | 500 -- 2,000 | 2 vCPU | 4 GB | 20 GB | Extra RAM for traffic bursts and session state |
| Large | 2,000 -- 10,000 | 4 vCPU | 8 GB | 40 GB | accel-ppp needs more CPU for packet processing |

**RAM breakdown for a small deployment (2 GB total):**

| Consumer | Allocation | Notes |
|----------|:----------:|-------|
| Linux kernel + systemd | ~200 MB | Base OS overhead |
| dawos-agent | ~64 MB | Stable regardless of endpoint count |
| accel-ppp | ~6 MB + ~2 KB/session | Scales linearly with session count |
| Swap safety buffer | — | Covered by swap file (see below) |
| **Available for caching/burst** | **~1.5 GB** | OS page cache, subprocess overhead |

Even at 500 concurrent sessions, accel-ppp adds only ~1 MB of memory. The 2 GB configuration provides over 1 GB of headroom.

---

## Log Rotation

### Why This Matters

On a 10 GB disk, unmanaged logs can fill the partition within weeks. A full disk causes service failures, prevents config checkpoint creation, and can make the system unresponsive.

### Configure journald Limits

Edit `/etc/systemd/journald.conf`:

```ini
[Journal]
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=30day
Compress=yes
```

Apply the changes:

```bash
sudo systemctl restart systemd-journald
```

Verify the current journal disk usage:

```bash
sudo journalctl --disk-usage
```

If the journal is already oversized, vacuum it immediately:

```bash
# Reduce to 500 MB now
sudo journalctl --vacuum-size=500M

# Or remove entries older than 30 days
sudo journalctl --vacuum-time=30d
```

### Application Log Volume Estimation

DawOS Agent log volume depends on the `DAWOS_LOG_FORMAT` and traffic patterns:

| Log Format | Approx. Size per Request | 1,000 req/day | 10,000 req/day |
|------------|:------------------------:|:--------------:|:--------------:|
| `text` | ~200 bytes | ~6 MB/month | ~60 MB/month |
| `json` | ~400 bytes | ~12 MB/month | ~120 MB/month |

Audit log entries (write operations only) add roughly 300 bytes each in JSON format.

With `SystemMaxUse=500M`, journald automatically manages rotation. No additional logrotate configuration is needed for the agent's stdout/stderr logs.

### Monitoring Disk Space

Add a cron job to alert when disk usage exceeds 80%:

```bash
# /etc/cron.d/disk-alert
*/15 * * * * root df / --output=pcent | tail -1 | tr -d ' %' | \
  awk '$1 > 80 {print "DISK WARNING: " $1 "% used"}' | \
  logger -t disk-check -p local0.warning
```

Or use the Prometheus node exporter metric:

```promql
# Alert when root partition is above 85%
node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} < 0.15
```

---

## Swap Configuration

### Why This Matters

The dev server currently runs with **zero swap**. While 2 GB RAM is sufficient for normal operations, a swap file provides a safety net against unexpected memory spikes (large accel-cmd output, many concurrent API requests, or OS memory pressure from updates).

Without swap, the Linux OOM killer may terminate accel-ppp or DawOS Agent if memory is exhausted. Losing accel-ppp disconnects all active PPPoE sessions.

### Create a Swap File

```bash
# Create a 1 GB swap file
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Verify
free -h
```

Make it persistent across reboots:

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Recommended Swap Size

| System RAM | Swap Size | Rationale |
|:----------:|:---------:|-----------|
| 2 GB | 1 GB | Safety net for memory spikes |
| 4 GB | 2 GB | Standard recommendation |
| 8 GB+ | 2 GB | Diminishing returns beyond 2 GB |

### Tune Swappiness

For a BNG node, avoid aggressive swapping. Set `vm.swappiness` to a low value so the kernel only uses swap under real memory pressure:

```bash
# Set immediately
sudo sysctl vm.swappiness=10

# Make persistent
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
```

The default value (60) is too aggressive for a network appliance where latency matters.

---

## Process Supervision

### The Risk

DawOS Agent is a single Python process. If it crashes or becomes unresponsive, remote API management is unavailable until the process restarts. However, **PPPoE sessions are not affected** — accel-ppp runs as a completely separate process and continues serving subscribers independently.

### Automatic Restart

The systemd unit file should include restart directives:

```ini
# /etc/systemd/system/dawos-agent.service
[Service]
Restart=always
RestartSec=3
WatchdogSec=30
StartLimitIntervalSec=300
StartLimitBurst=5
```

| Directive | Value | Purpose |
|-----------|-------|---------|
| `Restart=always` | — | Restart on any exit (crash, signal, clean exit) |
| `RestartSec=3` | 3 seconds | Wait before restarting to avoid tight crash loops |
| `WatchdogSec=30` | 30 seconds | systemd kills the process if it stops responding |
| `StartLimitIntervalSec=300` | 5 minutes | Window for counting restart attempts |
| `StartLimitBurst=5` | 5 attempts | Max restarts within the window before giving up |

Verify the current unit configuration:

```bash
sudo systemctl cat dawos-agent | grep -E 'Restart|Watchdog|StartLimit'
```

If any directive is missing, add it via an override:

```bash
sudo systemctl edit dawos-agent
```

```ini
[Service]
Restart=always
RestartSec=3
WatchdogSec=30
StartLimitIntervalSec=300
StartLimitBurst=5
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart dawos-agent
```

### Monitoring Agent Uptime

Use the Prometheus scrape target health to detect agent downtime:

```yaml
# /etc/prometheus/rules/dawos.yml
groups:
  - name: dawos-agent
    rules:
      - alert: DawosAgentDown
        expr: up{job="dawos-agent"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "dawos-agent is unreachable on {{ $labels.instance }}"
          description: >
            The agent has not responded to Prometheus scrapes for over
            2 minutes. Remote management is unavailable. PPPoE sessions
            are unaffected. Check: sudo systemctl status dawos-agent
```

### Health Check Script

For environments without Prometheus, use a simple health check script:

```bash
#!/usr/bin/env bash
# /usr/local/bin/dawos-health-check.sh

ENDPOINT="http://localhost:8470/health"
TIMEOUT=5

if ! curl -sf --max-time "$TIMEOUT" "$ENDPOINT" > /dev/null 2>&1; then
    echo "$(date -Iseconds) dawos-agent health check failed" | \
        logger -t dawos-health -p local0.crit

    # Attempt restart
    sudo systemctl restart dawos-agent

    echo "$(date -Iseconds) dawos-agent restarted" | \
        logger -t dawos-health -p local0.warning
fi
```

Schedule it via cron:

```bash
# /etc/cron.d/dawos-health
*/2 * * * * root /usr/local/bin/dawos-health-check.sh
```

---

## Scaling Beyond a Single Node

### Current Architecture (Single Node)

```
                    BNG Node
              +------------------+
  Operator ---| dawos-agent:8470 |
  Billing  ---|   accel-ppp      |
              +------------------+
```

This architecture is appropriate for:

- Single-site ISPs with one BNG node.
- Small to medium ISPs (up to ~5,000 subscribers on one node).
- Lab and development environments.

### Multi-Node Architecture

For ISPs operating multiple BNG nodes, dawos-cli provides built-in multi-node management:

```
              Operator Workstation
              +------------------+
              |   dawos-cli      |
              |   (multi-node)   |
              +--------+---------+
                       |
          +------------+------------+
          |            |            |
    +-----+----+ +----+-----+ +----+-----+
    | BNG-01   | | BNG-02   | | BNG-03   |
    | agent    | | agent    | | agent    |
    | :8470    | | :8470    | | :8470    |
    +----------+ +----------+ +----------+
```

dawos-cli node groups allow running commands across multiple nodes:

```bash
# Define a node group
dawos node add bng-01 --url http://10.0.1.1:8470 --key KEY1
dawos node add bng-02 --url http://10.0.1.2:8470 --key KEY2
dawos node group create production --nodes bng-01,bng-02

# Execute across all nodes
dawos node exec production -- session list
dawos node exec production -- system health
```

### Centralized Orchestration

For larger deployments (10+ nodes, automated subscriber lifecycle), consider adding a central orchestrator between the billing system and the BNG agents:

```
  Billing System
       |
  +----+----+
  | Central  |  (isp-agent, Temporal workflows)
  | Orches.  |
  +----+----+
       |
  +----+----+----+----+
  |    |    |    |    |
 BNG  BNG  BNG  BNG  BNG
  01   02   03   04   05
```

Benefits of central orchestration:

- **Workflow coordination** — Multi-step operations (activate subscriber: provision RADIUS, configure OLT, assign IP pool) are managed as a single transaction.
- **Retry and rollback** — Failed operations are automatically retried or rolled back.
- **Audit centralization** — All operations are logged in one place.
- **Multi-vendor support** — The orchestrator abstracts differences between BNG vendors.

This is the role of `isp-agent` in the broader ecosystem.

---

## Security Hardening

### Network Isolation

The agent API port (8470) should only be accessible from the management network:

```bash
# Allow management network only
sudo nft add rule inet filter input ip saddr 192.168.0.0/16 tcp dport 8470 accept
sudo nft add rule inet filter input tcp dport 8470 drop
```

Or configure the agent to listen only on the management interface:

```bash
# /etc/dawos-agent/agent.env
DAWOS_HOST=10.0.1.1
```

### API Key Strength

Generate a strong random API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Recommended minimum: 32 characters, URL-safe random string. Avoid short or predictable keys.

### File Permissions

Verify permissions after installation:

```bash
# agent.env should be readable only by root and dawos
sudo chown root:dawos /etc/dawos-agent/agent.env
sudo chmod 0640 /etc/dawos-agent/agent.env

# accel-ppp config should be writable by dawos (for config management)
sudo chown dawos:dawos /etc/accel-ppp.conf
sudo chown -R dawos:dawos /etc/accel-ppp.d/

# venv should be owned by dawos
sudo chown -R dawos:dawos /opt/dawos-agent/
```

### Disable Unnecessary Services

On a BNG node, remove or disable services that are not needed:

```bash
# Remove snap (frees ~40 MB RAM)
sudo apt remove --purge snapd
sudo rm -rf /snap /var/snap /var/lib/snapd

# Disable unneeded services
sudo systemctl disable --now packagekit
sudo systemctl disable --now unattended-upgrades
```

### SSH Hardening

Restrict SSH access to key-based authentication:

```bash
# /etc/ssh/sshd_config
PasswordAuthentication no
PermitRootLogin no
AllowUsers danu
MaxAuthTries 3
```

---

## Backup Strategy

### What to Back Up

| Item | Path | Frequency | Method |
|------|------|-----------|--------|
| accel-ppp config | `/etc/accel-ppp.conf` | Before every change | Config checkpoint API |
| Config checkpoints | `/etc/accel-ppp.d/` | Daily | rsync to backup server |
| Agent config | `/etc/dawos-agent/agent.env` | After changes | Manual copy |
| RADIUS database | MySQL/MariaDB | Hourly | mysqldump |
| Systemd units | `/etc/systemd/system/dawos-agent.service` | After changes | Version control |

### Automated Config Backup Script

```bash
#!/usr/bin/env bash
# /usr/local/bin/dawos-backup.sh

BACKUP_DIR="/var/backups/dawos"
DATE=$(date +%Y%m%d-%H%M%S)
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

# Create a checkpoint via the API
curl -sf -X POST -H "X-API-Key: $DAWOS_API_KEY" \
  http://localhost:8470/api/v1/config/checkpoint > /dev/null

# Archive config files
tar czf "$BACKUP_DIR/dawos-config-$DATE.tar.gz" \
  /etc/accel-ppp.conf \
  /etc/accel-ppp.d/ \
  /etc/dawos-agent/agent.env \
  2>/dev/null

# Remove old backups
find "$BACKUP_DIR" -name "dawos-config-*.tar.gz" -mtime +$KEEP_DAYS -delete

echo "$(date -Iseconds) backup completed: dawos-config-$DATE.tar.gz" | \
  logger -t dawos-backup
```

Schedule via cron:

```bash
# /etc/cron.d/dawos-backup
0 2 * * * root DAWOS_API_KEY=YOUR_KEY /usr/local/bin/dawos-backup.sh
```

---

## Post-Hardening Checklist

After applying these recommendations, verify each item:

```bash
# 1. Journal rotation configured
grep SystemMaxUse /etc/systemd/journald.conf

# 2. Swap is active
free -h | grep Swap

# 3. Swappiness is low
cat /proc/sys/vm/swappiness  # expect: 10

# 4. Systemd restart policy in place
sudo systemctl show dawos-agent --property=Restart  # expect: always

# 5. File permissions correct
ls -la /etc/dawos-agent/agent.env  # expect: -rw-r----- root dawos
ls -la /etc/accel-ppp.conf         # expect: owned by dawos

# 6. Agent is running and healthy
curl -sf http://localhost:8470/health
curl -sf http://localhost:8470/health/ready

# 7. Metrics are being scraped
curl -sf http://localhost:8470/metrics | grep dawos_http_requests_total

# 8. Disk space is healthy
df -h / | awk 'NR==2 {print "Disk usage: " $5}'

# 9. Swap file persists across reboot
grep swapfile /etc/fstab

# 10. API key is strong (at least 32 chars)
sudo grep DAWOS_API_KEY /etc/dawos-agent/agent.env | \
  awk -F= '{print "Key length: " length($2) " chars"}'
```

All 10 checks should pass before considering the node production-ready.
