# dawos-agent API Reference

REST API reference for dawos-agent.

**Base URL:** `http://<node-ip>:8470`

**Content-Type:** `application/json`

---

## Authentication

All endpoints except `GET /health` and `GET /health/ready` require an API key passed via the `X-API-Key` header.

```
X-API-Key: your-secret-api-key
```

Requests without a valid key receive:

```json
{
  "detail": "Invalid or missing API key"
}
```

| Status | Meaning |
|--------|---------|
| `401`  | Missing or invalid `X-API-Key` header |

---

## Common Patterns

- **Success responses** return the documented response model with HTTP 200 (or 201/204 where noted).
- **Error responses** return `{"detail": "<message>"}` with an appropriate HTTP status code.
- **Validation errors** return HTTP 422 with a JSON array describing the invalid field and constraint. All request body fields are validated against type constraints and regex patterns before reaching service logic. See [Input Validation Reference](validation-rules.md) for the complete list of patterns and per-field constraints.
- **Rate limiting** — All API endpoints are subject to per-IP rate limiting (default: 120 requests/minute). Health endpoints are exempt. Exceeding the limit returns HTTP 429 with a `Retry-After` header indicating when the client can retry.
- **Request tracing** — Every response includes an `X-Request-ID` header containing a UUID v4 trace ID. Clients can send their own `X-Request-ID` to correlate requests across services. The same ID appears in server logs when JSON logging is enabled.
- **SSE endpoints** return `text/event-stream` content type for real-time streaming.

### Interactive API Documentation

The agent serves built-in API documentation powered by OpenAPI:

| URL | Format | Description |
|-----|--------|-------------|
| `/docs` | Swagger UI | Interactive API explorer with "Try it out" functionality |
| `/redoc` | ReDoc | Read-friendly API reference with nested schemas |
| `/openapi.json` | OpenAPI 3.x | Machine-readable schema for code generation and tooling |

These endpoints are public (no authentication required).

---

## API Versioning

All API endpoints are served under the `/api/v1/` prefix. The versioning strategy follows these principles:

| Aspect | Policy |
|--------|--------|
| **Scheme** | URI path prefix (`/api/v1/`, `/api/v2/`, ...) |
| **Backward compatibility** | Minor and patch releases never break existing request/response contracts within the same major version |
| **New fields** | New optional fields may be added to response models without a version bump (additive changes are non-breaking) |
| **Deprecation** | If a v2 is introduced, v1 endpoints remain available for at least two minor release cycles with deprecation notices in response headers |
| **Health endpoints** | `/health` and `/health/ready` are unversioned — they are stable, public contracts |

Current version: **v1** (stable since 0.1.0).

---

## 1. Health

Public probes for liveness and readiness checks — no authentication required.

### GET /health

Lightweight liveness check for load balancers and orchestrators. Always returns HTTP 200 if the agent process is running.

**Auth:** Not required

**Response:**

```json
{
  "status": "ok",
  "node_name": "bng-node-01",
  "version": "0.2.0",
  "uptime_seconds": 3621.5,
  "timestamp": "2026-07-07T00:00:00Z"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Agent process is running |

### GET /health/ready

Readiness probe that verifies the agent can communicate with its dependencies. Checks accel-ppp CLI connectivity via `accel-cmd show version` with a 5-second timeout.

**Auth:** Not required

**Response (ready):**

```json
{
  "ready": true,
  "checks": [
    {"name": "accel-ppp", "status": "ok", "detail": "1.13.0-git-f4014a4"}
  ]
}
```

**Response (not ready):**

```json
{
  "ready": false,
  "checks": [
    {"name": "accel-ppp", "status": "error", "detail": "Connection refused"}
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | All dependencies reachable |
| `503`  | One or more dependencies unreachable |

---

## 2. System

Host-level system information and resource metrics.

### GET /api/v1/system/info

Return full system information including hardware, OS, and network interfaces.

**Auth:** Required

**Response:**

```json
{
  "hostname": "bng-node-01",
  "os": "Ubuntu 22.04",
  "kernel": "5.15.0-generic",
  "arch": "x86_64",
  "cpu": {
    "count": 8,
    "percent": 23.5,
    "load_avg": [1.2, 0.9, 0.7]
  },
  "memory": {
    "total_mb": 16384,
    "used_mb": 8192,
    "available_mb": 8192,
    "percent": 50.0
  },
  "disk": {
    "total_gb": 500.0,
    "used_gb": 120.0,
    "free_gb": 380.0,
    "percent": 24.0
  },
  "interfaces": [
    {
      "name": "eth0",
      "addresses": ["10.0.0.1"],
      "is_up": true
    }
  ],
  "boot_time": "2026-07-01T08:00:00Z"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `401`  | Unauthorized |

### GET /api/v1/system/metrics

Quick resource-usage metrics snapshot for monitoring dashboards.

**Auth:** Required

**Response:**

```json
{
  "cpu": {
    "count": 8,
    "percent": 23.5,
    "load_avg": [1.2, 0.9, 0.7]
  },
  "memory": {
    "total_mb": 16384,
    "used_mb": 8192,
    "available_mb": 8192,
    "percent": 50.0
  },
  "disk": {
    "total_gb": 500.0,
    "used_gb": 120.0,
    "free_gb": 380.0,
    "percent": 24.0
  },
  "timestamp": "2026-07-07T00:00:00Z"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `401`  | Unauthorized |

---

## 3. Service Management

Control the accel-ppp systemd service and execute whitelisted commands.

### GET /api/v1/service/status

Check accel-ppp service status.

**Auth:** Required

**Response:**

```json
{
  "name": "accel-ppp",
  "status": "running",
  "pid": 12345,
  "uptime": "3d 4h",
  "version": "1.13.0"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `running`, `stopped`, or `unknown` |

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/service/{action}

Start, stop, restart, or reload accel-ppp.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `action` | path | string | `start`, `stop`, `restart`, or `reload` |

**Response:**

```json
{
  "action": "restart",
  "success": true,
  "message": "Service restart successful"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Action completed |
| `500`  | systemctl or reload command failed |

### POST /api/v1/service/command

Execute a whitelisted accel-cmd command.

**Auth:** Required

**Allowed commands:** `show stat`, `show sessions`, `show ippool`, `show version`, `reload`, and patterns `show sessions *`, `terminate *`, `shaper *`, `pppoe mac-filter *`.

**Request body:**

```json
{
  "command": "show stat"
}
```

**Response:**

```json
{
  "success": true,
  "output": "...",
  "command": "show stat"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Command executed |
| `403`  | Command not in whitelist |

---

## 4. Sessions

PPPoE session listing, statistics, search, and termination.

### GET /api/v1/sessions

List all active PPPoE sessions.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "sessions": [
    {
      "ifname": "ppp0",
      "username": "user@isp",
      "ip": "10.0.0.10",
      "calling-sid": "AA:BB:CC:DD:EE:FF",
      "rate-limit": "5M/20M",
      "type": "pppoe",
      "state": "active",
      "uptime": "1d 2h",
      "rx-bytes": "1234567",
      "tx-bytes": "7654321"
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `500`  | accel-cmd failed |

### GET /api/v1/sessions/stats

Return session statistics and IP pool usage.

**Auth:** Required

**Response:**

```json
{
  "active": 150,
  "starting": 2,
  "finishing": 0,
  "cpu_percent": "12",
  "pool_used": "150",
  "pool_total": "1024",
  "uptime": "3d 4h"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `500`  | accel-cmd failed |

### GET /api/v1/sessions/find/{username}

Find sessions for a specific username.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `username` | path | string | PPPoE username to search for |

**Response:** Same schema as `GET /api/v1/sessions`.

| Status | Meaning |
|--------|---------|
| `200`  | Success (count may be 0) |
| `500`  | accel-cmd failed |

### POST /api/v1/sessions/terminate

Terminate a PPPoE session by username or interface name.

**Auth:** Required

**Request body:**

```json
{
  "username": "user@isp",
  "ifname": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string\|null | No* | Terminate by username |
| `ifname` | string\|null | No* | Terminate by interface name |

> *At least one of `username` or `ifname` must be provided.

**Response:**

```json
{
  "success": true,
  "message": "Session user@isp terminated"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Termination attempted |
| `400`  | Neither username nor ifname provided |

---

## 5. Session Control

Advanced session management: lookup by SID/IP, snapshots, restart, and bulk drop.

### GET /api/v1/sessions/control/by-sid/{sid}

Look up a session by accel-ppp session ID.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `sid` | path | string | accel-ppp session ID |

**Response:**

```json
{
  "found": true,
  "session": { "ifname": "ppp0", "username": "user@isp", "ip": "10.0.0.10" }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Lookup completed (check `found` field) |
| `500`  | Lookup failed |

### GET /api/v1/sessions/control/by-ip/{ip}

Look up a session by assigned IP address.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `ip` | path | string | Assigned IP address |

**Response:** Same schema as `by-sid`.

| Status | Meaning |
|--------|---------|
| `200`  | Lookup completed |
| `500`  | Lookup failed |

### GET /api/v1/sessions/control/snapshot/{username}

Get a detailed session snapshot with traffic counters.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `username` | path | string | PPPoE username |

**Response:**

```json
{
  "username": "user@isp",
  "found": true,
  "sessions": [
    { "ifname": "ppp0", "ip": "10.0.0.10", "uptime": "1d 2h" }
  ],
  "count": 1
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Snapshot retrieved |
| `500`  | Snapshot failed |

### POST /api/v1/sessions/control/restart

Terminate a session so the CPE reconnects.

**Auth:** Required

**Request body:**

```json
{
  "username": "user@isp"
}
```

**Response:**

```json
{
  "success": true,
  "username": "user@isp",
  "previous_interface": "ppp0",
  "message": "Session terminated, CPE will reconnect"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restart attempted |
| `500`  | Command failed |

### POST /api/v1/sessions/control/drop-by-mac

Drop all sessions from a specific MAC address.

**Auth:** Required

**Request body:**

```json
{
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

**Response:**

```json
{
  "success": true,
  "dropped": 2,
  "message": "Dropped 2 sessions for AA:BB:CC:DD:EE:FF"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Drop attempted |
| `500`  | Command failed |

---

## 6. Configuration

Read and update the accel-ppp configuration file.

### GET /api/v1/config

Read the current accel-ppp configuration file.

**Auth:** Required

**Response:**

```json
{
  "path": "/etc/accel-ppp.conf",
  "content": "[modules]\n...",
  "last_modified": "2026-07-06T10:00:00Z"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | Config file not found |

### PUT /api/v1/config

Update the accel-ppp configuration file.

**Auth:** Required

**Request body:**

```json
{
  "content": "[modules]\nlog_syslog\npppoe\n...",
  "restart_service": false,
  "backup": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content` | string | — | New configuration file content |
| `restart_service` | bool | `false` | Restart accel-ppp after writing |
| `backup` | bool | `true` | Create a timestamped backup first |

**Response:**

```json
{
  "success": true,
  "message": "Config updated and service restarted",
  "backup_path": "/etc/accel-ppp.conf.20260707-000000.bak"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Config written |
| `500`  | Write or restart failed |

### GET /api/v1/config/backups

List available configuration backups.

**Auth:** Required

**Response:**

```json
[
  {
    "name": "accel-ppp.conf.20260706.bak",
    "size": 4096,
    "created": "2026-07-06T10:00:00"
  }
]
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

---

## 7. Configuration Checkpoint

Diff, rollback, and guarded apply with auto-rollback timer.

### GET /api/v1/config/revisions

List all configuration checkpoint revisions.

**Auth:** Required

**Response:**

```json
{
  "count": 3,
  "revisions": [
    {
      "name": "accel-ppp.conf.20260706.checkpoint",
      "size": 4096,
      "created": "2026-07-06T10:00:00",
      "is_checkpoint": true
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/config/diff

Compute a unified diff between the running config and a backup.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `backup_name` | query | string | Filename of the backup to diff against |

**Response:**

```json
{
  "diff": "--- current\n+++ backup\n@@ -1,3 +1,3 @@...",
  "changed": true
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Diff computed |
| `404`  | Backup file not found |

### POST /api/v1/config/rollback/{backup_name}

Restore a previous configuration revision.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `backup_name` | path | string | Filename of the backup to restore |

**Response:**

```json
{
  "success": true,
  "message": "Config rolled back from accel-ppp.conf.20260706.bak",
  "safety_backup": "/etc/accel-ppp.conf.20260707-pre-rollback.bak"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Rollback applied |
| `404`  | Backup file not found |

### POST /api/v1/config/apply

Apply new config with auto-rollback timer. The operator must call `POST /confirm` within the deadline or the config reverts automatically.

**Auth:** Required

**Request body:**

```json
{
  "content": "[modules]\nlog_syslog\n...",
  "confirm_minutes": 5
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content` | string | — | New config content |
| `confirm_minutes` | int | `5` | Auto-rollback timeout (1–30 min) |

**Response:**

```json
{
  "success": true,
  "message": "Config applied — confirm within 5m or auto-rollback",
  "checkpoint": "accel-ppp.conf.20260707.checkpoint",
  "confirm_deadline_seconds": 300
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Config applied, timer started |
| `500`  | Apply failed |

### POST /api/v1/config/confirm

Confirm a pending guarded apply and cancel the auto-rollback timer.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "Config confirmed — auto-rollback cancelled"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Confirmed |
| `409`  | No pending apply to confirm |

### GET /api/v1/config/apply/status

Check whether a guarded apply is pending confirmation.

**Auth:** Required

**Response:**

```json
{
  "pending": true,
  "checkpoint": "accel-ppp.conf.20260707.checkpoint"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Status returned |

---

## 8. Network

Manage network interfaces, VLANs, static routes, and DNS.

### GET /api/v1/network/interfaces

List all network interfaces with addresses and state.

**Auth:** Required

**Response:**

```json
{
  "count": 3,
  "interfaces": [
    {
      "name": "eth0",
      "index": 2,
      "mac_address": "00:11:22:33:44:55",
      "mtu": 1500,
      "state": "UP",
      "flags": ["UP", "BROADCAST", "MULTICAST"],
      "addresses": [
        {
          "family": "inet",
          "address": "10.0.0.1",
          "prefix_len": 24,
          "broadcast": "10.0.0.255",
          "scope": "global"
        }
      ],
      "link_type": "ether"
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/network/interfaces/{name}

Get detailed information for a specific interface.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Interface name (e.g. `eth0`) |

**Response:** Single `InterfaceDetail` object (same shape as list items above).

| Status | Meaning |
|--------|---------|
| `200`  | Found |
| `404`  | Interface not found |

### PUT /api/v1/network/interfaces/{name}

Configure a network interface (add/remove address, change MTU, set state).

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Interface name |

**Request body:**

```json
{
  "address": "10.0.0.2/24",
  "remove_address": null,
  "mtu": 9000,
  "state": "up"
}
```

All fields are optional — only provided fields are applied.

**Response:**

```json
{
  "success": true,
  "message": "Interface configured",
  "interface": "eth0"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Applied |
| `400`  | Invalid parameters |

### GET /api/v1/network/vlans

Auto-detect all 802.1Q VLANs on the system.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "vlans": [
    {
      "name": "eth0.100",
      "parent": "eth0",
      "vlan_id": 100,
      "protocol": "802.1Q",
      "state": "UP",
      "mac_address": "00:11:22:33:44:55",
      "mtu": 1500,
      "addresses": []
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/network/vlans

Create a VLAN sub-interface.

**Auth:** Required

**Request body:**

```json
{
  "parent": "eth0",
  "vlan_id": 100,
  "address": "10.100.0.1/24"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `parent` | string | Yes | Parent interface |
| `vlan_id` | int | Yes | VLAN ID (1–4094) |
| `address` | string\|null | No | Optional IP in CIDR notation |

**Response:**

```json
{
  "success": true,
  "message": "VLAN 100 created on eth0",
  "name": "eth0.100"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Created |
| `400`  | Invalid parameters |

### PUT /api/v1/network/vlans/{name}

Set a VLAN interface's administrative state (up/down).

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | VLAN interface name |

**Request body:**

```json
{
  "state": "up"
}
```

**Response:**

```json
{
  "success": true,
  "message": "VLAN eth0.100 set up",
  "name": "eth0.100",
  "state": "up"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | State changed |
| `422`  | Invalid state value |
| `400`  | Operation failed |

### DELETE /api/v1/network/vlans/{name}

Delete a VLAN sub-interface.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | VLAN interface name (e.g. `eth0.100`) |

**Response:**

```json
{
  "success": true,
  "message": "VLAN eth0.100 deleted",
  "name": "eth0.100"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Deleted |
| `400`  | Deletion failed |

### GET /api/v1/network/routes

Show the IPv4 routing table.

**Auth:** Required

**Response:**

```json
{
  "count": 5,
  "routes": [
    {
      "destination": "default",
      "gateway": "10.0.0.1",
      "device": "eth0",
      "protocol": "static",
      "scope": "global",
      "metric": 100,
      "source": null
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/network/routes

Add a static route.

**Auth:** Required

**Request body:**

```json
{
  "destination": "192.168.1.0/24",
  "gateway": "10.0.0.1",
  "device": "eth0",
  "metric": 100
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `destination` | string | Yes | CIDR or `default` |
| `gateway` | string | Yes | Next-hop gateway |
| `device` | string\|null | No | Outgoing interface |
| `metric` | int\|null | No | Route metric |

**Response:**

```json
{
  "success": true,
  "message": "Route added"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Added |
| `400`  | Invalid parameters |

### DELETE /api/v1/network/routes

Delete a route from the routing table.

**Auth:** Required

**Request body:**

```json
{
  "destination": "192.168.1.0/24",
  "gateway": "10.0.0.1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `destination` | string | Yes | CIDR or `default` |
| `gateway` | string\|null | No | Gateway to disambiguate |

**Response:**

```json
{
  "success": true,
  "message": "Route deleted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Deleted |
| `400`  | Deletion failed |

### GET /api/v1/network/dns

Show current DNS configuration from `/etc/resolv.conf`.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "OK",
  "config": {
    "nameservers": ["8.8.8.8", "8.8.4.4"],
    "search_domains": ["example.com"]
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### PUT /api/v1/network/dns

Update DNS configuration in `/etc/resolv.conf`.

**Auth:** Required

**Request body:**

```json
{
  "nameservers": ["8.8.8.8", "1.1.1.1"],
  "search_domains": ["example.com"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `nameservers` | string[] | Yes | 1–3 nameserver IPs |
| `search_domains` | string[] | No | Search domain suffixes |

**Response:**

```json
{
  "success": true,
  "message": "DNS updated",
  "config": {
    "nameservers": ["8.8.8.8", "1.1.1.1"],
    "search_domains": ["example.com"]
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `500`  | Write failed |

---

## 9. Firewall

Manage nftables firewall, IP forwarding sysctl, and SNMP.

### GET /api/v1/firewall/status

Check the overall firewall status.

**Auth:** Required

**Response:**

```json
{
  "enabled": true,
  "backend": "nftables",
  "rules_count": 42,
  "nat_enabled": true,
  "sysctl": {
    "ip_forward": true,
    "ip6_forward": false
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/firewall/rules

List the full nftables ruleset.

**Auth:** Required

**Response:**

```json
{
  "raw_output": "table ip filter { ... }",
  "rules_count": 42
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/firewall/save

Persist the current nftables ruleset to `/etc/nftables.conf`.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "Ruleset saved to /etc/nftables.conf"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Saved |
| `500`  | Save failed |

### POST /api/v1/firewall/validate

Dry-run validate an nftables ruleset without applying it.

**Auth:** Required

**Request body:**

```json
{
  "ruleset": "table ip filter { chain input { type filter hook input priority 0; } }"
}
```

**Response:**

```json
{
  "valid": true,
  "detail": ""
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Validation completed |
| `400`  | Missing `ruleset` field |

### GET /api/v1/firewall/sysctl

Read current IP forwarding sysctl values.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "OK",
  "status": {
    "ip_forward": true,
    "ip6_forward": false
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### PUT /api/v1/firewall/sysctl

Enable or disable IP forwarding.

**Auth:** Required

**Request body:**

```json
{
  "ip_forward": true,
  "ip6_forward": false
}
```

**Response:**

```json
{
  "success": true,
  "message": "IPv4 forward=on, IPv6 forward=off",
  "status": {
    "ip_forward": true,
    "ip6_forward": false
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `500`  | sysctl write failed |

### GET /api/v1/firewall/conntrack

Return `nf_conntrack_max` and current usage.

**Auth:** Required

**Response:**

```json
{
  "current_max": 262144,
  "recommended_min": 262144,
  "status": "ok",
  "detail": "Conntrack table size is adequate"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### PUT /api/v1/firewall/conntrack

Set `nf_conntrack_max` and persist.

**Auth:** Required

**Request body:**

```json
{
  "max_value": 524288
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_value` | int | Yes | New value (minimum 16384) |

**Response:** Same schema as `GET /api/v1/firewall/conntrack`.

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `500`  | sysctl write failed |

### GET /api/v1/firewall/snmp

Check SNMP daemon status and UDP port availability.

**Auth:** Required

**Response:**

```json
{
  "running": true,
  "port_open": true,
  "detail": "snmpd running, port 161 open"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

---

## 10. Firewall Groups

Manage nftables named sets (address, network, and port groups).

### GET /api/v1/firewall/groups

List all firewall groups.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "groups": [
    {
      "name": "blocked_ips",
      "type": "address",
      "elements": ["10.0.0.5", "10.0.0.6"]
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/firewall/groups

Create a new firewall group.

**Auth:** Required — **Status:** `201 Created`

**Request body:**

```json
{
  "name": "blocked_ips",
  "group_type": "address",
  "elements": ["10.0.0.5"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Group name |
| `group_type` | string | Yes | `address`, `network`, or `port` |
| `elements` | string[] | No | Initial elements |

**Response:**

```json
{
  "success": true,
  "message": "Group created",
  "name": "blocked_ips",
  "type": "address"
}
```

| Status | Meaning |
|--------|---------|
| `201`  | Created |
| `400`  | Invalid type or elements |

### DELETE /api/v1/firewall/groups/{name}

Delete a firewall group.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Group name to delete |

**Response:**

```json
{
  "success": true,
  "message": "Group deleted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Deleted |

### POST /api/v1/firewall/groups/{name}/members

Add members to an existing firewall group.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Group name |

**Request body:**

```json
{
  "elements": ["10.0.0.7", "10.0.0.8"]
}
```

**Response:**

```json
{
  "success": true,
  "message": "Members added"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Added |

---

## 11. NAT

Per-subscriber egress NAT, masquerade, and box-level egress control.

### POST /api/v1/firewall/nat/masquerade

Enable NAT masquerade on a WAN interface. Idempotent.

**Auth:** Required

**Request body:**

```json
{
  "wan_interface": "eth0"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Masquerade enabled on eth0",
  "wan_interface": "eth0"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Enabled |
| `400`  | Invalid interface |

### DELETE /api/v1/firewall/nat/masquerade

Remove the NAT masquerade table and rules.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "Masquerade removed",
  "wan_interface": ""
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Removed |
| `400`  | Removal failed |

### GET /api/v1/firewall/nat/status

Return comprehensive NAT status.

**Auth:** Required

**Response:**

```json
{
  "egress_map": [
    { "customer_ip": "10.0.0.10", "public_ip": "203.0.113.1" }
  ],
  "postrouting_rules": "...",
  "bound_ips": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/firewall/nat/egress

List per-subscriber egress NAT mappings.

**Auth:** Required

**Response:**

```json
{
  "entries": [
    { "customer_ip": "10.0.0.10", "public_ip": "203.0.113.1" }
  ],
  "count": 1
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/firewall/nat/egress

Map a subscriber IP to a public egress IP.

**Auth:** Required

**Request body:**

```json
{
  "target": "10.0.0.10",
  "public_ip": "203.0.113.1"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Egress mapping created"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Created |
| `400`  | Mapping failed |

### DELETE /api/v1/firewall/nat/egress/{customer_ip}

Remove a subscriber's egress NAT mapping.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `customer_ip` | path | string | Subscriber IP |

**Response:**

```json
{
  "success": true,
  "message": "Egress mapping removed"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Removed |
| `400`  | Removal failed |

### POST /api/v1/firewall/nat/public-ip

Bind a public IP address to the uplink interface.

**Auth:** Required

**Request body:**

```json
{
  "public_ip": "203.0.113.2",
  "interface": "eth0"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `public_ip` | string | Yes | Public IP to add |
| `interface` | string | No | Uplink interface (auto-detected if empty) |

**Response:**

```json
{
  "success": true,
  "message": "Public IP bound"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Bound |
| `400`  | Binding failed |

### DELETE /api/v1/firewall/nat/public-ip/{public_ip}

Remove a public IP from the uplink interface.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `public_ip` | path | string | Public IP to remove |

**Response:**

```json
{
  "success": true,
  "message": "Public IP removed"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Removed |
| `400`  | Removal failed |

### GET /api/v1/firewall/nat/box-egress

Check whether box-level egress NAT (accelnat table) is enabled.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "OK",
  "enabled": true
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/firewall/nat/box-egress

Toggle box-level egress NAT on or off.

**Auth:** Required

**Request body:**

```json
{
  "action": "on"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | `on` or `off` |

**Response:**

```json
{
  "success": true,
  "message": "Box egress enabled",
  "enabled": true
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Toggled |
| `400`  | Invalid action value |

---

## 12. PPPoE

Manage PPPoE listener interfaces and MAC address filters.

### GET /api/v1/pppoe/interfaces

List PPPoE listener interfaces from the accel-ppp config.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "interfaces": [
    { "name": "eth0.100", "options": "padi-limit=0" },
    { "name": "eth0.200", "options": "" }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | Config file not found |

### POST /api/v1/pppoe/interfaces

Add a PPPoE listener interface and reload accel-ppp.

**Auth:** Required

**Request body:**

```json
{
  "interface": "eth0.300",
  "options": "padi-limit=0"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `interface` | string | Yes | Interface name to add |
| `options` | string | No | Comma-separated options |

**Response:**

```json
{
  "success": true,
  "message": "Interface eth0.300 added"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Added |
| `404`  | Config file not found |
| `409`  | Interface already configured |

### DELETE /api/v1/pppoe/interfaces/{name}

Remove a PPPoE listener interface and reload accel-ppp.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Interface name to remove |

**Response:**

```json
{
  "success": true,
  "message": "Interface eth0.300 removed"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Removed |
| `404`  | Config or interface not found |

### GET /api/v1/pppoe/mac-filter

List PPPoE MAC address filter entries.

**Auth:** Required

**Response:**

```json
{
  "raw_output": "AA:BB:CC:DD:EE:FF\n11:22:33:44:55:66",
  "count": 2
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/pppoe/mac-filter

Add a MAC address to the PPPoE filter.

**Auth:** Required

**Request body:**

```json
{
  "mac": "AA:BB:CC:DD:EE:FF"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Added AA:BB:CC:DD:EE:FF"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Added |

### DELETE /api/v1/pppoe/mac-filter/{mac}

Remove a MAC address from the PPPoE filter.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `mac` | path | string | MAC address to remove |

**Response:**

```json
{
  "success": true,
  "message": "Removed AA:BB:CC:DD:EE:FF"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Removed |

---

## 13. PPPoE PADO Delay

Control PADO (PPPoE Active Discovery Offer) delay settings.

### GET /api/v1/pppoe/pado

Read the current PADO delay configuration.

**Auth:** Required

**Response:**

```json
{
  "delay": 100,
  "min_sessions": 50,
  "description": "100ms delay after 50 active sessions"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | Config file not found |

### PUT /api/v1/pppoe/pado

Set the PADO delay and reload accel-ppp.

**Auth:** Required

**Request body:**

```json
{
  "delay": 200,
  "min_sessions": 100
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `delay` | int | Yes | PADO delay in ms (0 disables) |
| `min_sessions` | int | No | Apply delay after N sessions (default 0) |

**Response:** Same schema as `GET /api/v1/pppoe/pado`.

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `400`  | Invalid values |
| `404`  | Config file not found |

---

## 14. Traffic & Rate Limiting

Real-time traffic monitoring (SSE), queue stats, and shaper overrides.

### GET /api/v1/traffic/stream/{username}

Stream per-user throughput via Server-Sent Events.

**Auth:** Required

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `username` | path | string | — | PPPoE username to monitor |
| `interval` | query | float | `2.0` | Sampling interval in seconds |

**Response:** `text/event-stream` with JSON payloads:

```
data: {"username":"user@isp","download_mbps":15.2,"upload_mbps":3.1,"rx_bytes":123456,"tx_bytes":654321}
```

### GET /api/v1/traffic/stream

Stream aggregate throughput for all sessions via SSE.

**Auth:** Required

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `interval` | query | float | `2.0` | Sampling interval in seconds |

**Response:** `text/event-stream` with per-session throughput data.

### GET /api/v1/traffic/queue/{username}

Return tc shaper queue statistics for a user's session.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `username` | path | string | PPPoE username |

**Response:**

```json
{
  "username": "user@isp",
  "ifname": "ppp0",
  "qdisc": "htb",
  "classes": "...",
  "filters": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | No active session |

### POST /api/v1/traffic/ratelimit/{username}

Temporarily override a session's shaper rate.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `username` | path | string | PPPoE username |

**Request body:**

```json
{
  "rate": "5M/20M"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rate` | string | Yes | Rate in `up/down` format (e.g. `5M/20M`) |

**Response:**

```json
{
  "success": true,
  "message": "Rate changed",
  "username": "user@isp",
  "rate": "5M/20M"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Rate applied |
| `404`  | No active session |

### DELETE /api/v1/traffic/ratelimit/{username}

Restore a session's shaper to the RADIUS-assigned value.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `username` | path | string | PPPoE username |

**Response:**

```json
{
  "success": true,
  "message": "Rate restored",
  "username": "user@isp",
  "rate": "restored"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restored |
| `404`  | No active session |

---

## 15. Routing (BGP, OSPF, RIP, BFD)

Query FRRouting dynamic routing protocol status via `vtysh`.

### GET /api/v1/routing/bgp/status

Return the BGP summary.

**Auth:** Required

**Response:**

```json
{
  "configured": true,
  "router_id": "10.0.0.1",
  "local_as": "65001",
  "neighbors": [
    {
      "neighbor": "10.0.0.2",
      "remote_as": "65002",
      "state": "Established",
      "up_down": "1d 2h",
      "prefixes_received": 150
    }
  ],
  "total_prefixes": 150,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/bgp/routes

Return BGP IPv4 unicast routes.

**Auth:** Required

**Response:**

```json
{
  "count": 150,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/ospf/status

Return OSPF status.

**Auth:** Required

**Response:**

```json
{
  "configured": true,
  "router_id": "10.0.0.1",
  "neighbors": [
    {
      "neighbor_id": "10.0.0.2",
      "priority": 1,
      "state": "Full",
      "address": "10.0.0.2",
      "interface": "eth0"
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/ospf/neighbors

Return the OSPF neighbor table.

**Auth:** Required

**Response:** Same schema as `GET /api/v1/routing/ospf/status`.

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/ospf/routes

Return OSPF routes.

**Auth:** Required

**Response:**

```json
{
  "count": 25,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/rip/status

Return RIP protocol status.

**Auth:** Required

**Response:**

```json
{
  "configured": true,
  "version": "2",
  "networks": ["10.0.0.0/24"],
  "neighbors": ["10.0.0.2"],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/rip/routes

Return RIP routing table entries.

**Auth:** Required

**Response:**

```json
{
  "count": 10,
  "routes": [
    {
      "code": "R(n)",
      "network": "192.168.1.0/24",
      "nexthop": "10.0.0.2",
      "metric": 2
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/bfd/peers

Return BFD peer status.

**Auth:** Required

**Response:**

```json
{
  "configured": true,
  "peers": [
    {
      "peer": "10.0.0.2",
      "interface": "eth0",
      "status": "Up",
      "uptime": "1d 2h"
    }
  ],
  "count": 1,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/routing/bfd/summary

Return BFD counters summary.

**Auth:** Required

**Response:**

```json
{
  "configured": true,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

---

## 16. Conntrack

Advanced conntrack table tuning, timeouts, helpers, and profiles.

### GET /api/v1/conntrack/config

Read current conntrack table configuration.

**Auth:** Required

**Response:**

```json
{
  "table_size": 262144,
  "current_count": 15000,
  "hash_size": 65536,
  "usage_percent": 5.7
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### PUT /api/v1/conntrack/table-size

Set the `nf_conntrack_max` table size.

**Auth:** Required

**Request body:**

```json
{
  "size": 524288
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `size` | int | Yes | New value (16384–50000000) |

**Response:** Same schema as `GET /api/v1/conntrack/config`.

| Status | Meaning |
|--------|---------|
| `200`  | Updated |

### GET /api/v1/conntrack/timeouts

Read all conntrack protocol timeouts.

**Auth:** Required

**Response:**

```json
{
  "timeouts": {
    "tcp_timeout_established": 432000,
    "tcp_timeout_close": 10,
    "udp_timeout": 30
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### PUT /api/v1/conntrack/timeouts

Set a single conntrack timeout value.

**Auth:** Required

**Request body:**

```json
{
  "key": "tcp_timeout_established",
  "seconds": 300000
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Sysctl timeout key |
| `seconds` | int | Yes | Timeout in seconds (min 1) |

**Response:** Same schema as `GET /api/v1/conntrack/timeouts`.

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `400`  | Invalid key or value |

### GET /api/v1/conntrack/helpers

List loaded conntrack helper (ALG) modules.

**Auth:** Required

**Response:**

```json
{
  "count": 3,
  "helpers": [
    { "module": "nf_conntrack_ftp", "size": 24576, "used_by": 0 }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/conntrack/profiles

List available conntrack tuning profiles.

**Auth:** Required

**Response:**

```json
{
  "profiles": ["default", "gaming", "streaming"]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/conntrack/profiles/apply

Apply a named conntrack tuning profile.

**Auth:** Required

**Request body:**

```json
{
  "name": "gaming"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Profile name: `default`, `gaming`, or `streaming` |

**Response:** Same schema as `GET /api/v1/conntrack/timeouts`.

| Status | Meaning |
|--------|---------|
| `200`  | Applied |
| `400`  | Unknown profile |

---

## 17. Connection Limits

Manage accel-ppp session and rate-limit caps.

### GET /api/v1/limits

Read global session limits.

**Auth:** Required

**Response:**

```json
{
  "max_sessions": 0,
  "max_starting": 0,
  "session_timeout": 0
}
```

> `0` means unlimited.

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | Config file not found |

### PUT /api/v1/limits

Update global session limits and reload accel-ppp.

**Auth:** Required

**Request body:**

```json
{
  "max_sessions": 500,
  "max_starting": 50
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_sessions` | int\|null | No | Max concurrent sessions (0 = unlimited) |
| `max_starting` | int\|null | No | Max sessions in starting state |

**Response:** Same schema as `GET /api/v1/limits`.

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `404`  | Config file not found |

### GET /api/v1/limits/interface/{name}

Read the PADI rate-limit for a specific PPPoE interface.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | PPPoE interface name |

**Response:**

```json
{
  "interface": "eth0.100",
  "padi_limit": 100,
  "found": true
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | Config or interface not found |

---

## 18. IP Pool

Manage IP address pools used for PPPoE subscriber assignment.

### GET /api/v1/ip-pool

List all configured IP pools.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "pools": [
    { "name": "pool1", "range": "10.0.0.0/24" },
    { "name": "pool2", "range": "10.0.1.0/24" }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `404`  | Config file not found |

### POST /api/v1/ip-pool

Add a new IP pool and reload accel-ppp.

**Auth:** Required — **Status:** `201 Created`

**Request body:**

```json
{
  "name": "pool3",
  "ip_range": "10.0.2.0/24"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Pool name label |
| `ip_range` | string | Yes | CIDR range |

**Response:**

```json
{
  "success": true,
  "message": "Pool pool3 added"
}
```

| Status | Meaning |
|--------|---------|
| `201`  | Created |
| `404`  | Config file not found |
| `409`  | Pool name already exists |

### DELETE /api/v1/ip-pool/{name}

Remove an IP pool by name and reload accel-ppp.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Pool name to remove |

**Response:**

```json
{
  "success": true,
  "message": "Pool pool3 removed"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Removed |
| `404`  | Pool or config not found |

### GET /api/v1/ip-pool/usage

Get real-time IP pool utilisation statistics.

**Auth:** Required

**Response:**

```json
{
  "used": "150",
  "total": "1024",
  "available": "874"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

---

## 19. Scheduler

CRUD management of recurring scheduled jobs.

### GET /api/v1/scheduler/jobs

List all scheduled jobs.

**Auth:** Required

**Response:**

```json
{
  "count": 1,
  "jobs": [
    {
      "name": "cleanup-logs",
      "command": "journalctl --vacuum-time=7d",
      "interval_seconds": 86400,
      "enabled": true,
      "last_run": "2026-07-06T23:00:00Z",
      "last_result": { "returncode": 0, "output": "..." },
      "run_count": 7
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/scheduler/jobs

Register a new scheduled job.

**Auth:** Required — **Status:** `201 Created`

**Request body:**

```json
{
  "name": "cleanup-logs",
  "command": "journalctl --vacuum-time=7d",
  "interval_seconds": 86400,
  "enabled": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique job name |
| `command` | string | Yes | Shell command to execute |
| `interval_seconds` | int | Yes | Repeat interval (min 10) |
| `enabled` | bool | No | Active on schedule (default `true`) |

**Response:** Single `SchedulerJobResponse` object.

| Status | Meaning |
|--------|---------|
| `201`  | Created |
| `409`  | Job name already exists |

### DELETE /api/v1/scheduler/jobs/{name}

Remove a scheduled job. Returns `204 No Content` on success.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Job name to remove |

| Status | Meaning |
|--------|---------|
| `204`  | Deleted |
| `404`  | Job not found |

### POST /api/v1/scheduler/jobs/{name}/run

Execute a scheduled job immediately.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Job name to execute |

**Response:**

```json
{
  "success": true,
  "output": "Vacuuming done...",
  "returncode": 0,
  "timestamp": "2026-07-07T00:00:00Z"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Executed |
| `404`  | Job not found |

---

## 20. DNS Forwarding

Manage the dnsmasq DNS forwarding service.

### GET /api/v1/dns/forwarding/status

Check dnsmasq service status.

**Auth:** Required

**Response:**

```json
{
  "running": true,
  "backend": "dnsmasq",
  "upstream_count": 2
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/dns/forwarding/config

Read the current DNS forwarding configuration.

**Auth:** Required

**Response:**

```json
{
  "servers": ["8.8.8.8", "8.8.4.4"],
  "listen_address": "127.0.0.1",
  "cache_size": 1000
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### PUT /api/v1/dns/forwarding/config

Set upstream DNS servers and cache size.

**Auth:** Required

**Request body:**

```json
{
  "servers": ["8.8.8.8", "1.1.1.1"],
  "cache_size": 5000
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `servers` | string[] | Yes | 1–5 upstream DNS servers |
| `cache_size` | int | No | Cache size (0–100000, default 1000) |

**Response:** Same schema as `GET /api/v1/dns/forwarding/config`.

| Status | Meaning |
|--------|---------|
| `200`  | Updated |
| `500`  | Write or restart failed |

### POST /api/v1/dns/forwarding/flush

Flush the dnsmasq DNS cache.

**Auth:** Required

**Response:**

```json
{
  "flushed": true
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Flushed |
| `500`  | Flush failed |

---

## 21. NTP

Query NTP synchronisation status via `chronyc`.

### GET /api/v1/ntp/status

Return NTP synchronisation status.

**Auth:** Required

**Response:**

```json
{
  "synced": true,
  "reference": "time.google.com",
  "stratum": 2,
  "system_time_offset": "+0.000123s",
  "last_offset": "-0.000045s",
  "frequency": "+1.234ppm",
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/ntp/sources

Return configured NTP time sources.

**Auth:** Required

**Response:**

```json
{
  "count": 4,
  "sources": [
    {
      "tally": "*",
      "name": "time.google.com",
      "stratum": 1,
      "poll": 64,
      "reach": "377",
      "detail": "..."
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

---

## 22. LLDP

Query Link Layer Discovery Protocol neighbors via `lldpctl`.

### GET /api/v1/lldp/status

Check the LLDP daemon status.

**Auth:** Required

**Response:**

```json
{
  "running": true,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/lldp/neighbors

List all discovered LLDP neighbors.

**Auth:** Required

**Response:**

```json
{
  "count": 3,
  "neighbors": [
    {
      "local_interface": "eth0",
      "chassis_name": "switch-01",
      "port_id": "GigabitEthernet0/1",
      "port_description": "Uplink to BNG",
      "ttl": "120"
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/lldp/neighbors/{name}

Get LLDP neighbors for a specific interface.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Interface name |

**Response:**

```json
{
  "interface": "eth0",
  "found": true,
  "neighbors": [ ... ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

---

## 23. DHCP

Monitor and control DHCP server and relay services.

### GET /api/v1/dhcp/status

Check the DHCP server status.

**Auth:** Required

**Response:**

```json
{
  "active": true,
  "service": "isc-dhcp-server",
  "lease_count": 50,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/dhcp/leases

List all active DHCP leases.

**Auth:** Required

**Response:**

```json
{
  "count": 50,
  "leases": [
    {
      "expires": 1720310400,
      "mac": "AA:BB:CC:DD:EE:FF",
      "ip": "192.168.1.10",
      "hostname": "client-01",
      "client_id": "01:AA:BB:CC:DD:EE:FF"
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/dhcp/relay/status

Check the DHCP relay agent status.

**Auth:** Required

**Response:**

```json
{
  "active": true,
  "service": "isc-dhcp-relay",
  "config": { "server": "10.0.0.1", "interface": "eth0" },
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/dhcp/restart

Restart the DHCP server.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "DHCP server restarted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restarted |
| `500`  | Restart failed |

### POST /api/v1/dhcp/relay/restart

Restart the DHCP relay agent.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "message": "DHCP relay restarted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restarted |
| `500`  | Restart failed |

---

## 24. Flow Accounting

Monitor NetFlow/sFlow/IPFIX flow-accounting daemons.

### GET /api/v1/flow/status

Check the flow accounting daemon status.

**Auth:** Required

**Response:**

```json
{
  "active": true,
  "daemon": "softflowd",
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/flow/collectors

List configured flow collectors.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "collectors": [
    {
      "host": "10.0.0.5",
      "port": 9996,
      "protocol": "netflow9",
      "source": "10.0.0.1"
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/flow/stats

Retrieve flow accounting statistics.

**Auth:** Required

**Response:**

```json
{
  "flows_exported": 1500000,
  "packets_processed": 50000000,
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/flow/restart

Restart the flow accounting daemon.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "daemon": "softflowd",
  "message": "Flow daemon restarted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restarted |
| `500`  | Restart failed |

---

## 25. Event Handler

Register webhooks/scripts and fire events.

### GET /api/v1/events/hooks

List all registered event hooks.

**Auth:** Required

**Response:**

```json
{
  "count": 2,
  "hooks": [
    {
      "name": "notify-session-up",
      "event": "session.up",
      "action": "https://webhook.example.com/session",
      "enabled": true,
      "fire_count": 42
    }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/events/hooks

Register a new event hook.

**Auth:** Required — **Status:** `201 Created`

**Request body:**

```json
{
  "name": "notify-session-up",
  "event": "session.up",
  "action": "https://webhook.example.com/session",
  "enabled": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique hook name |
| `event` | string | Yes | Event type to listen for |
| `action` | string | Yes | Webhook URL or shell command |
| `enabled` | bool | No | Active immediately (default `true`) |

**Response:** Single `EventHookResponse` object.

| Status | Meaning |
|--------|---------|
| `201`  | Created |
| `409`  | Hook name already exists |

### DELETE /api/v1/events/hooks/{name}

Remove an event hook. Returns `204 No Content`.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `name` | path | string | Hook name to remove |

| Status | Meaning |
|--------|---------|
| `204`  | Deleted |
| `404`  | Hook not found |

### POST /api/v1/events/fire

Fire an event manually.

**Auth:** Required

**Request body:**

```json
{
  "event": "session.up",
  "payload": { "username": "user@isp", "ip": "10.0.0.10" }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event` | string | Yes | Event type to dispatch |
| `payload` | object | No | Arbitrary JSON payload |

**Response:**

```json
{
  "event": "session.up",
  "hooks_fired": 2,
  "results": [ ... ],
  "timestamp": "2026-07-07T00:00:00Z"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Fired |
| `400`  | Invalid event name |

### GET /api/v1/events/history

Retrieve the event history log.

**Auth:** Required

**Response:**

```json
{
  "count": 100,
  "entries": [
    { "event": "session.up", "timestamp": "2026-07-07T00:00:00Z", "hooks_fired": 1 }
  ]
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### DELETE /api/v1/events/history

Clear the event history log.

**Auth:** Required

**Response:**

```json
{
  "cleared": 100
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Cleared |

---

## 26. Zone Firewall

Manage nftables zone-based firewall policies.

### GET /api/v1/zones

List all firewall zones.

**Auth:** Required

**Response:**

```json
{
  "count": 3,
  "zones": [
    { "name": "wan", "type": "", "description": "" },
    { "name": "lan", "type": "", "description": "" }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/zones/{zone}

Get detailed rules for a firewall zone.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `zone` | path | string | Zone name |

**Response:**

```json
{
  "zone": "wan",
  "found": true,
  "rules": [
    { "chain": "input", "rule": "tcp dport 22 accept" }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/zones

Create a new firewall zone.

**Auth:** Required — **Status:** `201 Created`

**Request body:**

```json
{
  "name": "dmz",
  "interfaces": ["eth2"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Zone name |
| `interfaces` | string[] | No | Interfaces to bind |

**Response:**

```json
{
  "success": true,
  "message": "Zone dmz created"
}
```

| Status | Meaning |
|--------|---------|
| `201`  | Created |

### DELETE /api/v1/zones/{zone}

Delete a firewall zone.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `zone` | path | string | Zone name to delete |

**Response:**

```json
{
  "success": true,
  "message": "Zone dmz deleted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Deleted |

---

## 27. VRRP

Manage keepalived VRRP high-availability groups.

### GET /api/v1/vrrp/status

Return VRRP / keepalived status.

**Auth:** Required

**Response:**

```json
{
  "active": true,
  "service": "keepalived",
  "groups": [
    {
      "name": "VI_1",
      "state": "MASTER",
      "priority": 100,
      "vip": "10.0.0.100"
    }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/vrrp/groups/{group}

Get detailed information for a VRRP group.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `group` | path | string | VRRP group name |

**Response:**

```json
{
  "found": true,
  "group": {
    "name": "VI_1",
    "state": "MASTER",
    "priority": 100,
    "vip": "10.0.0.100"
  }
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/vrrp/failover

Trigger a manual VRRP failover.

**Auth:** Required

**Request body:**

```json
{
  "group": "VI_1"
}
```

**Response:**

```json
{
  "success": true,
  "group": "VI_1",
  "message": "Failover triggered"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Triggered |
| `500`  | Failover failed |

### POST /api/v1/vrrp/restart

Restart the keepalived service.

**Auth:** Required

**Response:**

```json
{
  "success": true,
  "group": "",
  "message": "keepalived restarted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restarted |
| `500`  | Restart failed |

---

## 28. Monitoring

Manage Prometheus and SNMP monitoring exporters.

### GET /api/v1/monitoring/status

Retrieve monitoring stack status.

**Auth:** Required

**Response:**

```json
{
  "exporters": [
    { "service": "node_exporter", "active": true, "port": 9100 },
    { "service": "snmp_exporter", "active": false, "port": 9116 }
  ],
  "count": 2
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### GET /api/v1/monitoring/metrics/{service}

Get metrics from a specific monitoring exporter.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `service` | path | string | Exporter service name |

**Response:**

```json
{
  "service": "node_exporter",
  "available": true,
  "metrics": [
    { "name": "node_cpu_seconds_total", "value": "12345.67" }
  ],
  "raw_output": "..."
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |

### POST /api/v1/monitoring/configure

Enable or disable a monitoring exporter.

**Auth:** Required

**Request body:**

```json
{
  "service": "snmp_exporter",
  "enable": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | string | Yes | Exporter service name |
| `enable` | bool | No | `true` to enable, `false` to disable (default `true`) |

**Response:**

```json
{
  "success": true,
  "service": "snmp_exporter",
  "enabled": true,
  "message": "Exporter enabled"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Configured |

### POST /api/v1/monitoring/restart/{service}

Restart a monitoring exporter service.

**Auth:** Required

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| `service` | path | string | Exporter service name |

**Response:**

```json
{
  "success": true,
  "service": "node_exporter",
  "message": "Exporter restarted"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Restarted |
| `500`  | Restart failed |

---

## 29. Diagnostics

Comprehensive BNG health checks.

### GET /api/v1/diagnostics/doctor

Run all BNG health checks and return aggregated results.

**Auth:** Required

**Response:**

```json
{
  "checks": [
    { "name": "config_syntax", "status": "ok", "detail": "Config is valid" },
    { "name": "service_status", "status": "ok", "detail": "accel-ppp running" },
    { "name": "pool_usage", "status": "warn", "detail": "Pool 85% full" }
  ],
  "total": 3,
  "fails": 0,
  "warns": 1,
  "healthy": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `checks[].status` | string | `ok`, `warn`, or `fail` |
| `healthy` | bool | `true` if no checks failed |

| Status | Meaning |
|--------|---------|
| `200`  | Diagnostics completed |
| `500`  | Diagnostic runner failed |

---

## 30. Logs

Retrieve and stream accel-ppp logs from the systemd journal.

### GET /api/v1/logs/tail

Return the last N log lines from a systemd journal unit.

**Auth:** Required

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `lines` | query | int | `100` | Number of lines to return |
| `unit` | query | string | `accel-ppp` | Systemd unit name |

**Response:**

```json
{
  "lines": [
    "Jul 07 00:00:01 bng accel-pppd[1234]: pppoe: session started",
    "Jul 07 00:00:02 bng accel-pppd[1234]: radius: access-accept"
  ],
  "count": 2,
  "source": "accel-ppp"
}
```

| Status | Meaning |
|--------|---------|
| `200`  | Success |
| `500`  | journalctl failed |

### GET /api/v1/logs/stream

Stream live log lines via Server-Sent Events.

**Auth:** Required

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `unit` | query | string | `accel-ppp` | Systemd unit name |

**Response:** `text/event-stream` — each new log line is emitted as an SSE event.

```
data: Jul 07 00:00:01 bng accel-pppd[1234]: pppoe: session started
```
