# Upgrade Guide

Step-by-step instructions for upgrading DawOS Agent on production and development BNG nodes.

---

## Before You Begin

### Prerequisites

- SSH access to the BNG node with `sudo` privileges.
- The node must have internet access to reach PyPI (or a local mirror).
- A maintenance window if the node serves active PPPoE subscribers -- the agent restart causes a brief API interruption (typically under 5 seconds). PPPoE sessions themselves are **not affected** by an agent restart; only the management API becomes temporarily unavailable.

### Check the Current Version

```bash
curl -sf http://localhost:8470/health | python3 -m json.tool
```

Look at the `version` field in the response. Compare with the latest release on [PyPI](https://pypi.org/project/dawos-agent/) or [GitHub Releases](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases).

### Read the Changelog

Before upgrading, review the [Changelog](../development/changelog.md) for breaking changes, new configuration options, and migration steps between your current version and the target version.

---

## Standard Upgrade (Recommended)

This is the standard procedure for upgrading to a new patch or minor release.

### Step 1: Back Up Configuration

```bash
sudo cp /etc/dawos-agent/agent.env /etc/dawos-agent/agent.env.bak
```

### Step 2: Upgrade the Package

```bash
sudo /opt/dawos-agent/venv/bin/pip install --upgrade dawos-agent
```

### Step 3: Restart the Service

```bash
sudo systemctl restart dawos-agent
```

### Step 4: Verify

```bash
# Check service status
sudo systemctl is-active dawos-agent

# Verify new version
curl -sf http://localhost:8470/health | python3 -m json.tool

# Test authenticated endpoint
curl -sf -H 'X-API-Key: YOUR_KEY' http://localhost:8470/api/v1/sessions

# Check for startup errors
sudo journalctl -u dawos-agent --since '2 minutes ago' --no-pager -p err
```

---

## Pin to a Specific Version

To upgrade to a specific version instead of the latest:

```bash
sudo /opt/dawos-agent/venv/bin/pip install dawos-agent==0.3.1
sudo systemctl restart dawos-agent
```

---

## Clean Reinstall

Use this when the virtualenv is corrupted, when upgrading across major Python versions, or when the standard upgrade fails.

### Step 1: Stop the Service

```bash
sudo systemctl stop dawos-agent
```

### Step 2: Back Up Configuration

```bash
sudo cp /etc/dawos-agent/agent.env /etc/dawos-agent/agent.env.bak
```

### Step 3: Recreate the Virtual Environment

```bash
sudo rm -rf /opt/dawos-agent/venv
sudo python3 -m venv /opt/dawos-agent/venv
sudo /opt/dawos-agent/venv/bin/pip install --upgrade pip
sudo /opt/dawos-agent/venv/bin/pip install dawos-agent
sudo chown -R dawos:dawos /opt/dawos-agent
```

### Step 4: Start and Verify

```bash
sudo systemctl start dawos-agent
sudo systemctl is-active dawos-agent
curl -sf http://localhost:8470/health | python3 -m json.tool
```

---

## Rollback

If the new version introduces problems, roll back to the previous version.

### Step 1: Identify the Previous Version

```bash
# Check pip install history
sudo /opt/dawos-agent/venv/bin/pip install dawos-agent==
```

This intentionally fails but prints all available versions. Note the version you were previously running.

### Step 2: Downgrade

```bash
sudo /opt/dawos-agent/venv/bin/pip install dawos-agent==0.1.0
sudo systemctl restart dawos-agent
```

### Step 3: Restore Configuration (If Needed)

If the upgrade modified configuration format:

```bash
sudo cp /etc/dawos-agent/agent.env.bak /etc/dawos-agent/agent.env
sudo systemctl restart dawos-agent
```

### Step 4: Verify

```bash
curl -sf http://localhost:8470/health | python3 -m json.tool
sudo journalctl -u dawos-agent --since '2 minutes ago' --no-pager -p err
```

---

## Upgrading Across Major Versions

Major version upgrades (e.g. 0.x to 1.x) may include breaking changes to the API contract, configuration format, or system requirements.

### Procedure

1. **Read the changelog carefully** -- major versions document all breaking changes and required migration steps.

2. **Test on a development node first** -- never upgrade production directly on a major bump.

3. **Update configuration** -- new required settings may need to be added to `agent.env`. The agent logs warnings at startup for missing configuration that was previously optional.

4. **Update API clients** -- if you use dawos-cli or custom scripts, upgrade them to a compatible version:
   ```bash
   pip install --upgrade dawos-cli
   ```

5. **Verify all endpoints** -- run a smoke test across the endpoint categories you use:
   ```bash
   # Health
   curl -sf http://localhost:8470/health

   # Sessions
   curl -sf -H 'X-API-Key: KEY' http://localhost:8470/api/v1/sessions

   # System info
   curl -sf -H 'X-API-Key: KEY' http://localhost:8470/api/v1/system/info

   # Metrics
   curl -sf http://localhost:8470/metrics | head -5
   ```

---

## Multi-Node Upgrade Strategy

When managing multiple BNG nodes, upgrade one at a time to limit blast radius.

### Rolling Upgrade

1. **Start with the development node** -- upgrade and verify before touching production.

2. **Upgrade one production node** -- verify for at least 15 minutes under real traffic.

3. **Upgrade remaining nodes** -- proceed only after the first node shows no issues.

### Automation Example

For environments with multiple BNG nodes, script the upgrade:

```bash
#!/bin/bash
# upgrade-dawos.sh -- upgrade dawos-agent on a remote BNG node

set -euo pipefail

NODE=$1
KEY=$2

echo "Upgrading dawos-agent on $NODE..."

ssh "$NODE" "sudo /opt/dawos-agent/venv/bin/pip install --upgrade dawos-agent"
ssh "$NODE" "sudo systemctl restart dawos-agent"

sleep 3

VERSION=$(ssh "$NODE" "curl -sf http://localhost:8470/health" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")
echo "Node $NODE upgraded to v$VERSION"

# Verify auth
STATUS=$(ssh "$NODE" "curl -s -o /dev/null -w '%{http_code}' -H 'X-API-Key: $KEY' http://localhost:8470/api/v1/sessions")
if [ "$STATUS" != "200" ]; then
  echo "WARNING: Auth check returned $STATUS on $NODE"
  exit 1
fi

echo "Upgrade verified on $NODE"
```

Usage:

```bash
./upgrade-dawos.sh user@bng-node YOUR_API_KEY
```

---

## Upgrading to v0.4.0

v0.4.0 introduces session history with a SQLite database stored at `/var/lib/dawos-agent/history.db`. This requires two additional setup steps that the `manage.sh` upgrade script handles automatically.

### If Using `manage.sh` (Recommended)

The upgrade script automatically:

1. Creates `/var/lib/dawos-agent/` with correct ownership
2. Adds `-/var/lib/dawos-agent` to the systemd `ReadWritePaths` directive
3. Reloads the systemd daemon

```bash
sudo bash scripts/manage.sh upgrade
```

No manual steps needed.

### If Upgrading Manually

After `pip install --upgrade dawos-agent`, perform these additional steps **before** restarting:

```bash
# 1. Create history database directory
sudo mkdir -p /var/lib/dawos-agent
sudo chown dawos:dawos /var/lib/dawos-agent

# 2. Add /var/lib/dawos-agent to systemd ReadWritePaths
#    (required because ProtectSystem=strict blocks writes to unlisted paths)
sudo sed -i 's|^ReadWritePaths=.*|& -/var/lib/dawos-agent|' \
    /etc/systemd/system/dawos-agent.service
sudo systemctl daemon-reload

# 3. Restart
sudo systemctl restart dawos-agent
```

### Verify History Feature

```bash
# Check history endpoints work
curl -sf -H 'X-API-Key: KEY' http://localhost:8470/api/v1/sessions/history
curl -sf -H 'X-API-Key: KEY' http://localhost:8470/api/v1/sessions/history/stats
```

### New Configuration Variable

| Variable | Default | Description |
|----------|---------|-------------|
| `DAWOS_HISTORY_DB` | `/var/lib/dawos-agent/history.db` | SQLite session history database path |

Add to `/etc/dawos-agent/agent.env` only if you need a non-default path.

---

## Post-Upgrade Checklist

After every upgrade, verify these items:

| Check | Command | Expected |
|-------|---------|----------|
| Service active | `sudo systemctl is-active dawos-agent` | `active` |
| Correct version | `curl -sf http://localhost:8470/health` | New version in response |
| Auth works | `curl -sf -H 'X-API-Key: KEY' http://localhost:8470/api/v1/sessions` | HTTP 200 |
| Auth rejects | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8470/api/v1/sessions` | `401` |
| accel-ppp connected | `curl -sf http://localhost:8470/health/ready` | `"ready": true` |
| Metrics available | `curl -sf http://localhost:8470/metrics \| head -5` | Prometheus text output |
| No startup errors | `sudo journalctl -u dawos-agent --since '5 min ago' -p err` | Empty or no relevant errors |
| History works (v0.4.0+) | `curl -sf -H 'X-API-Key: KEY' http://localhost:8470/api/v1/sessions/history` | HTTP 200 with JSON array |

---

## New Configuration Options

When a new version introduces configuration variables, the agent logs warnings at startup for settings that were not explicitly configured. These are informational -- defaults are applied automatically.

Check for new settings after upgrade:

```bash
sudo journalctl -u dawos-agent --since '2 minutes ago' | grep -i 'not configured\|new setting\|default'
```

Review the [Configuration Reference](../getting-started/configuration.md) for the complete list of available settings and their defaults.
