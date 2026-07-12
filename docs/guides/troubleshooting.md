# Troubleshooting

Common issues, symptoms, and resolution steps for DawOS Agent deployments.

---

## Quick Diagnostics

Run these commands first to identify the problem category:

```bash
# 1. Is the service running?
sudo systemctl is-active dawos-agent

# 2. Recent error logs
sudo journalctl -u dawos-agent --since '15 minutes ago' --no-pager -p err

# 3. Liveness check
curl -sf http://localhost:8470/health

# 4. Readiness check (accel-ppp connectivity)
curl -sf http://localhost:8470/health/ready

# 5. Auth check
curl -s -o /dev/null -w '%{http_code}' -H 'X-API-Key: YOUR_KEY' \
  http://localhost:8470/api/v1/sessions
```

---

## Service Will Not Start

### Symptom

`systemctl start dawos-agent` fails or the service exits immediately.

### Diagnosis

```bash
sudo systemctl status dawos-agent
sudo journalctl -u dawos-agent -n 50 --no-pager
```

### Common Causes

**Port already in use**

Another process is listening on port 8470.

```bash
sudo ss -tlnp | grep 8470
```

Resolution: Stop the conflicting process, or change the dawos-agent port in `/etc/dawos-agent/agent.env`:

```bash
DAWOS_PORT=8471
```

**Python virtual environment missing or corrupt**

```bash
/opt/dawos-agent/venv/bin/python --version
```

If this fails, recreate the virtualenv:

```bash
sudo python3 -m venv /opt/dawos-agent/venv
sudo /opt/dawos-agent/venv/bin/pip install --upgrade pip
sudo /opt/dawos-agent/venv/bin/pip install dawos-agent
sudo chown -R dawos:dawos /opt/dawos-agent
sudo systemctl restart dawos-agent
```

**Missing or malformed agent.env**

```bash
cat /etc/dawos-agent/agent.env
```

Verify the file exists and contains valid `KEY=VALUE` lines. No quotes around values, no trailing spaces.

---

## Authentication Failures (HTTP 401)

### Symptom

All API calls return `{"detail": "Invalid or missing API key"}` with HTTP 401.

### Diagnosis

```bash
# Check the configured key
sudo grep DAWOS_API_KEY /etc/dawos-agent/agent.env

# Test with the correct key
curl -sf -H 'X-API-Key: YOUR_KEY' http://localhost:8470/api/v1/sessions
```

### Common Causes

**Wrong API key in request**

The `X-API-Key` header value must exactly match `DAWOS_API_KEY` in `agent.env`. Check for leading/trailing whitespace.

**Key not reloaded after change**

After editing `agent.env`, you must restart the service:

```bash
sudo systemctl restart dawos-agent
```

The agent reads configuration at startup only.

---

## accel-ppp Connectivity Issues

### Symptom

`GET /health/ready` returns HTTP 503 with `"status": "error"` for the accel-ppp check. API calls that depend on accel-cmd return HTTP 500.

### Diagnosis

```bash
# Test accel-cmd directly
accel-cmd show version

# Check if accel-ppp is running
sudo systemctl status accel-ppp

# Verify CLI port
sudo ss -tlnp | grep 2001
```

### Common Causes

**accel-ppp service is stopped**

```bash
sudo systemctl start accel-ppp
sudo systemctl status accel-ppp
```

**CLI port mismatch**

The agent defaults to port 2001. If accel-ppp uses a different CLI port, update `agent.env`:

```bash
DAWOS_ACCEL_CLI_PORT=2001
```

Verify in `/etc/accel-ppp.conf`:

```ini
[cli]
telnet=127.0.0.1:2001
```

**accel-cmd binary not found**

```bash
which accel-cmd
ls -la /usr/bin/accel-cmd
```

If installed at a different path, update `agent.env`:

```bash
DAWOS_ACCEL_CMD=/usr/local/bin/accel-cmd
```

---

## HTTP 429 Rate Limit Exceeded

### Symptom

API responses return HTTP 429 with a `Retry-After` header.

### Diagnosis

```bash
# Check current rate limit setting
grep DAWOS_RATE_LIMIT /etc/dawos-agent/agent.env

# Check metrics for rate limit hits
curl -sf http://localhost:8470/metrics | grep rate_limit
```

### Resolution

**Increase the limit** if legitimate traffic exceeds the default (120/minute):

```bash
# /etc/dawos-agent/agent.env
DAWOS_RATE_LIMIT=300/minute
```

**Disable rate limiting** entirely (not recommended for production):

```bash
DAWOS_RATE_LIMIT=
```

Restart after changing:

```bash
sudo systemctl restart dawos-agent
```

---

## Configuration Backup/Restore Failures (HTTP 500)

### Symptom

Config backup, apply, or checkpoint operations return HTTP 500.

### Diagnosis

```bash
# Check file ownership
ls -la /etc/accel-ppp.conf
ls -la /etc/accel-ppp.d/
```

### Resolution

The `dawos` user needs write access to the accel-ppp config paths:

```bash
sudo chown dawos:dawos /etc/accel-ppp.conf
sudo chown -R dawos:dawos /etc/accel-ppp.d/
```

Verify the systemd unit has the paths in `ReadWritePaths`:

```bash
sudo systemctl cat dawos-agent | grep ReadWritePaths
```

Expected paths include `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/`.

---

## DNS Write Failures

### Symptom

DNS configuration endpoints return HTTP 500 when writing to `/etc/resolv.conf`.

### Diagnosis

```bash
ls -la /etc/resolv.conf
readlink -f /etc/resolv.conf
```

### Common Causes

**systemd-resolved symlink**

On Ubuntu, `/etc/resolv.conf` is often a symlink to a systemd-resolved stub. The agent uses `sudo tee` to write through the symlink, but the systemd sandbox must whitelist the path.

Verify the systemd unit includes `/etc/resolv.conf` in `ReadWritePaths`:

```bash
sudo systemctl cat dawos-agent | grep resolv
```

If missing, add it to the service override:

```bash
sudo systemctl edit dawos-agent
```

```ini
[Service]
ReadWritePaths=/etc/resolv.conf
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart dawos-agent
```

---

## Sudoers Permission Denied

### Symptom

Operations involving `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`, or `conntrack` fail with a "permission denied" or "not allowed" error in the logs.

### Diagnosis

```bash
# Check sudoers rules
sudo cat /etc/sudoers.d/dawos-agent

# Test a sudo command as the dawos user
sudo -u dawos sudo -n /usr/sbin/nft list ruleset
```

### Resolution

The sudoers file must allow the `dawos` user to run specific commands without a password. Expected content:

```
dawos ALL=(ALL) NOPASSWD: /usr/sbin/nft, /usr/sbin/ip, /usr/sbin/tc, /usr/sbin/vtysh, /usr/sbin/sysctl, /usr/bin/tee, /usr/sbin/conntrack
```

If missing or incorrect:

```bash
# Recreate the sudoers file
echo 'dawos ALL=(ALL) NOPASSWD: /usr/sbin/nft, /usr/sbin/ip, /usr/sbin/tc, /usr/sbin/vtysh, /usr/sbin/sysctl, /usr/bin/tee, /usr/sbin/conntrack' | \
  sudo tee /etc/sudoers.d/dawos-agent

# Set correct permissions
sudo chmod 0440 /etc/sudoers.d/dawos-agent

# Validate syntax
sudo visudo -c -f /etc/sudoers.d/dawos-agent
```

---

## NAT / Firewall Rule Failures

### Symptom

NAT masquerade, egress, or firewall operations return HTTP 500 or report that tables/chains do not exist.

### Diagnosis

```bash
# List current nftables ruleset
sudo nft list ruleset

# Check if nftables service is running
sudo systemctl status nftables

# Check for iptables conflicts
sudo iptables -L -n
```

### Common Causes

**nftables not installed or not running**

```bash
sudo apt install nftables
sudo systemctl enable --now nftables
```

**Missing base tables**

The agent creates tables and chains on demand, but certain operations require the base `inet` table to exist. If operations fail with "No such file or directory" errors, initialize the base ruleset:

```bash
sudo nft add table inet filter
sudo nft add chain inet filter input { type filter hook input priority 0 \; }
sudo nft add chain inet filter forward { type filter hook forward priority 0 \; }
sudo nft add chain inet filter output { type filter hook output priority 0 \; }
```

---

## Metrics Not Appearing in Prometheus

### Symptom

Prometheus scrape targets show `DOWN` status, or custom metrics (`dawos_*`) are missing from the `/metrics` response.

### Diagnosis

```bash
# Verify the endpoint responds
curl -sf http://localhost:8470/metrics | head -20

# Check for dawos-specific metrics
curl -sf http://localhost:8470/metrics | grep dawos_

# Verify from the Prometheus server
curl -sf http://<prometheus-host>:9090/api/v1/targets | python3 -m json.tool
```

### Common Causes

**Network connectivity**

Prometheus must be able to reach the agent on port 8470. Verify firewall rules allow the connection:

```bash
# From the Prometheus server
curl -sf http://<agent-ip>:8470/metrics
```

**Scrape config error**

Check `prometheus.yml` for correct target address:

```yaml
scrape_configs:
  - job_name: dawos-agent
    scrape_interval: 15s
    static_configs:
      - targets: ["10.0.1.1:8470"]
```

**Custom metrics only appear after first observation**

Counter and histogram metrics are registered at import time, but their label combinations only appear in the `/metrics` output after the first matching request. Send a test request to populate them:

```bash
curl -sf -H 'X-API-Key: YOUR_KEY' http://localhost:8470/api/v1/sessions
curl -sf http://localhost:8470/metrics | grep dawos_http_requests
```

---

## Slow API Responses

### Symptom

API calls take several seconds to return, or response times have degraded over time.

### Diagnosis

```bash
# Check request duration metrics
curl -sf http://localhost:8470/metrics | grep duration

# Check system resources
top -b -n1 | head -20
df -h
free -h

# Check accel-ppp responsiveness
time accel-cmd show stat
```

### Common Causes

**accel-cmd latency**

Most API endpoints invoke `accel-cmd` as a subprocess. If accel-ppp is under heavy load (thousands of sessions), CLI responses slow down, which directly increases API response time.

Monitor the `dawos_http_request_duration_seconds` histogram to identify which endpoints are slowest.

**System resource exhaustion**

High CPU, memory pressure, or disk I/O contention affect subprocess execution time. Check with standard Linux tools (`top`, `vmstat`, `iostat`).

**Retry overhead**

If `accel-cmd` frequently fails transiently, the retry mechanism adds delay. Check the retry counter:

```bash
curl -sf http://localhost:8470/metrics | grep retries
```

If `dawos_accel_cmd_retries_total` is growing fast, investigate the root cause of the transient failures rather than increasing retry limits.

---

## Log Analysis

### Viewing Logs

```bash
# Real-time log stream
sudo journalctl -u dawos-agent -f

# Recent errors only
sudo journalctl -u dawos-agent --since '1 hour ago' -p err --no-pager

# Audit trail (write operations only)
sudo journalctl -u dawos-agent --since today | grep 'AUDIT'

# Filter by request ID
sudo journalctl -u dawos-agent | grep 'abc123-request-id'
```

### JSON Log Parsing

When `DAWOS_LOG_FORMAT=json` is enabled, use `jq` for structured queries:

```bash
# All errors in the last hour
sudo journalctl -u dawos-agent --since '1 hour ago' --no-pager -o cat | \
  jq -r 'select(.level == "ERROR") | "\(.timestamp) \(.message)"'

# Audit trail grouped by endpoint
sudo journalctl -u dawos-agent --since today --no-pager -o cat | \
  jq -r 'select(.message | startswith("AUDIT")) | .message'

# Slow requests (>1 second)
sudo journalctl -u dawos-agent --since '1 hour ago' --no-pager -o cat | \
  jq -r 'select(.message | startswith("AUDIT")) |
    select(.message | test("duration_ms=[0-9]{4,}")) | .message'
```

---

## Getting Help

If the issue persists after following these steps:

1. Collect diagnostic output:
   ```bash
   sudo systemctl status dawos-agent
   sudo journalctl -u dawos-agent --since '1 hour ago' --no-pager
   curl -sf http://localhost:8470/health
   curl -sf http://localhost:8470/health/ready
   curl -sf http://localhost:8470/metrics | grep dawos_
   ```

2. Check the [Changelog](../development/changelog.md) for known issues and recent fixes.

3. Open an issue at [github.com/Cepat-Kilat-Teknologi/dawos-agent](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/issues) with the diagnostic output attached.
