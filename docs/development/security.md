# Security

This document describes the security architecture and practices used in DawOS Agent.

For vulnerability reporting, see the [Security Policy](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/SECURITY.md).

---

## Authentication

All API endpoints except `/health`, `/health/ready`, and `/metrics` require an `X-API-Key` header. Missing or invalid keys receive HTTP 401 Unauthorized.

```bash
# Authenticated request
curl -H "X-API-Key: your-key" http://bng-node:8470/api/v1/system/info

# Without key -> 401
curl http://bng-node:8470/api/v1/system/info
```

The WebSocket endpoint at `/ws/events` accepts the API key via the `X-API-Key` header (preferred) or as a `key` query parameter (fallback). Header-based authentication is preferred because query parameters may appear in server access logs and browser history.

### Generating a Strong API Key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

This produces a 43-character URL-safe base64 string with 256 bits of entropy.

---

## Role-Based Access Control (RBAC)

DawOS Agent supports three access tiers that restrict which endpoints a given API key can reach.

| Role | Allowed Methods | Restricted Endpoints |
|------|----------------|---------------------|
| viewer | GET only | Cannot access any write operations |
| operator | GET, POST, PUT, DELETE | Cannot access audit log, playbooks, service restart |
| admin | All methods, all endpoints | Full access |

### Single-Key Mode (Default)

The `DAWOS_API_KEY` environment variable defines a single key with admin access. This is the simplest setup and is backward compatible with versions before RBAC was introduced.

### Multi-Key Mode

For teams that need different access levels, create a JSON file mapping keys to roles:

```json
{
  "readonly-dashboard-key": "viewer",
  "noc-operator-key": "operator",
  "infra-admin-key": "admin"
}
```

Point `DAWOS_API_KEYS_FILE` at this file. The primary `DAWOS_API_KEY` always remains an admin key regardless of what the file contains.

### How RBAC Is Enforced

Each router endpoint declares its minimum required role. The RBAC middleware checks the authenticated key's role against the endpoint requirement and returns HTTP 403 Forbidden if the role is insufficient.

---

## Rate Limiting

Per-IP rate limiting protects the agent from abuse and accidental request floods.

| Setting | Default | Description |
|---------|---------|-------------|
| `DAWOS_RATE_LIMIT` | `120/minute` | Requests per IP per window |

When a client exceeds the limit, the agent returns HTTP 429 Too Many Requests with a `Retry-After` header indicating when the client can retry.

Exempt endpoints (not rate-limited):

- `GET /health`
- `GET /health/ready`
- `GET /metrics`

Rate limit violations are tracked by the `dawos_rate_limit_hits_total` Prometheus counter, which can be used for alerting on suspicious traffic patterns.

To disable rate limiting entirely, set `DAWOS_RATE_LIMIT` to an empty string.

---

## Systemd Sandboxing

The systemd service unit restricts the agent's access to the host system.

| Directive | Value | Purpose |
|-----------|-------|---------|
| `ProtectSystem` | `strict` | Makes the entire filesystem read-only except paths listed in `ReadWritePaths` |
| `ProtectHome` | `true` | Makes `/home`, `/root`, and `/run/user` inaccessible |
| `PrivateTmp` | `true` | Gives the service its own isolated `/tmp` directory |
| `NoNewPrivileges` | `false` | Set to false because the agent needs sudo for system commands |
| `Restart` | `always` | Restarts on any exit -- crash, clean exit, or signal |
| `WatchdogSec` | `30` | Kills the process if it becomes unresponsive for 30 seconds |
| `StartLimitBurst` | `5` | Maximum 5 restarts within the interval before systemd stops retrying |
| `StartLimitIntervalSec` | `300` | The 5-minute window for the restart burst limit |

### Writable Paths

Only the following paths are explicitly allowed for writes via `ReadWritePaths`:

| Path | Purpose |
|------|---------|
| `/etc/accel-ppp.conf` | accel-ppp main configuration |
| `/etc/accel-ppp.d` | accel-ppp configuration fragments |
| `/etc/accel-nat-egress.nft` | NAT egress nftables rules |
| `/etc/sysctl.d` | Kernel parameter overrides |
| `/etc/nftables.conf` | Main nftables configuration |
| `/etc/resolv.conf` | DNS resolver configuration |
| `/etc/systemd/resolved.conf.d` | systemd-resolved drop-in configs |
| `/etc/dnsmasq.d` | dnsmasq configuration fragments |
| `/etc/dnsmasq.conf` | dnsmasq main configuration |

All other filesystem locations are read-only to the service process.

---

## Least-Privilege Sudo

The `dawos` service user has passwordless sudo access for exactly 7 commands. No shell access, no wildcards, no unrestricted commands.

| Command | Full Path | Used By |
|---------|-----------|---------|
| `nft` | `/usr/sbin/nft` | Firewall rules, NAT, zone firewall |
| `ip` | `/usr/sbin/ip` | Network interfaces, VLANs, routes |
| `tc` | `/usr/sbin/tc` | Traffic shaping and QoS |
| `vtysh` | `/usr/bin/vtysh` | FRR routing daemon (BGP, OSPF, RIP, BFD) |
| `sysctl` | `/usr/sbin/sysctl` | Kernel parameter tuning |
| `tee` | `/usr/bin/tee` | Writing to system configuration files |
| `conntrack` | `/usr/sbin/conntrack` | Conntrack table flush |

The sudoers file is installed at `/etc/sudoers.d/dawos-agent` with mode `0440` owned by `root:root`.

---

## Subprocess Safety

DawOS Agent executes system commands to manage the BNG node. Several layers prevent command injection:

### List-Form Arguments

All subprocess calls use Python's `asyncio.create_subprocess_exec` with list-form arguments. The command and each argument are separate list elements, which prevents shell metacharacter interpretation.

```python
# How commands are executed (safe)
await asyncio.create_subprocess_exec("ip", "addr", "show", "ens18")

# What is NOT done (unsafe)
await asyncio.create_subprocess_shell(f"ip addr show {interface}")
```

### Defense-in-Depth: shlex.quote()

User-supplied values are passed through `shlex.quote()` before being used in subprocess arguments. This is a secondary defense layer -- even if a future code change accidentally introduced string interpolation, the quoting would prevent injection.

This defense is applied in the following service modules:

- `firewall_service.py`
- `nat_service.py`
- `network_service.py`
- `traffic_service.py`
- `config_service.py`

### No Dangerous Constructs

- **No `eval()` or `exec()`** anywhere in the codebase
- **No `shell=True`** in any subprocess call
- **No string interpolation** into shell commands
- **No `os.system()`** calls

---

## Input Validation

All API request bodies are validated by Pydantic v2 models before reaching any business logic. Invalid requests receive HTTP 422 with structured error details.

---

## Error Response Hardening

All HTTP 500 error responses return a generic `"Internal server error"` message
instead of exposing raw exception text. This prevents information disclosure of
internal paths, stack traces, and system details to API clients.

Client-facing 4xx errors (400, 404, 409, 422) retain descriptive messages since
those contain controlled, non-sensitive text that helps callers diagnose request
issues.

Internal error details are logged server-side at ERROR level with the full
exception message for debugging purposes.

Validation includes:

- **Type constraints** -- integers, strings, booleans, enums
- **Regex patterns** -- interface names, IP addresses, CIDR notation
- **Length limits** -- minimum and maximum string lengths
- **Enum values** -- restricted to known-good values for protocol types, actions, etc.

The config apply endpoint (`PUT /api/v1/config` and `POST /api/v1/checkpoint/apply`) has additional validation: content must be at least 10 characters to prevent accidental writes of empty or near-empty configurations.

---

## Webhook Security

When `DAWOS_WEBHOOK_URL` is configured, the agent sends HTTP POST notifications on every mutating (write) request.

### Payload Signing

Set `DAWOS_WEBHOOK_SECRET` to enable HMAC-SHA256 signing. The signature is sent in the `X-Dawos-Signature` header.

Consumers should verify the signature before processing:

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Delivery

- Webhook delivery sends an actual HTTP POST to the configured URL via `httpx.AsyncClient` with a 10-second timeout.
- Failures do not affect the API response.
- The webhook payload includes: event type, hook name, and optional context payload as JSON.
- The response status code is captured and `success` is set based on whether the status is below 400.

---

## Audit Log

All mutating requests (POST, PUT, DELETE) are recorded in an in-memory ring buffer with the following fields:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 UTC timestamp |
| `method` | HTTP method |
| `path` | Request path |
| `client_ip` | Client IP address |
| `request_id` | UUID v4 trace ID |
| `role` | RBAC role of the authenticated key |
| `status_code` | HTTP response status code |
| `duration_ms` | Request processing time |

The buffer size is configurable via `DAWOS_AUDIT_BUFFER_SIZE` (default: 1000 entries). When the buffer is full, the oldest entries are discarded.

Access the audit log via `GET /api/v1/audit` (admin role required).

---

## Request Tracing

Every HTTP request receives a UUID v4 trace ID:

- Returned in the `X-Request-ID` response header
- Injected into all log records for that request
- Included in webhook payloads and audit log entries

If the client sends an `X-Request-ID` header, the agent validates it against
the pattern `[\x20-\x7E]{1,128}` (printable ASCII, max 128 characters). Valid
values are preserved for distributed tracing; invalid or missing values are
replaced with a generated UUID v4. This prevents header injection and log
pollution from malformed trace IDs.

---

## File Permissions

### Configuration Files

| File | Mode | Owner | Contains |
|------|------|-------|----------|
| `/etc/dawos-agent/agent.env` | `0640` | `root:dawos` | API key and all DAWOS_* settings |
| `/etc/sudoers.d/dawos-agent` | `0440` | `root:root` | Sudo rules (7 commands) |

### accel-ppp Configuration

The installer sets ownership of `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/` to the `dawos` user. This is required for the config checkpoint and rollback system to function.

If you install manually without the installer, set this ownership:

```bash
sudo chown dawos:dawos /etc/accel-ppp.conf
sudo chown -R dawos:dawos /etc/accel-ppp.d/
```

Without correct ownership, config backup and rollback operations return HTTP 500.

---

## Network Isolation

### Listen Address

By default, DawOS Agent listens on `0.0.0.0:8470` (all interfaces). In production, restrict this to the management network:

```bash
# In /etc/dawos-agent/agent.env
DAWOS_HOST=10.0.0.1    # management interface only
# or
DAWOS_HOST=127.0.0.1   # localhost only (if using reverse proxy)
```

### TLS Termination

DawOS Agent does not handle TLS directly. Deploy it behind a reverse proxy for HTTPS:

- **nginx** -- standard reverse proxy with `proxy_pass http://127.0.0.1:8470`
- **Caddy** -- automatic HTTPS with `reverse_proxy localhost:8470`

### Firewall Rules

Restrict port 8470 to authorized management hosts:

```bash
# Allow only from management subnet
sudo nft add rule inet filter input tcp dport 8470 ip saddr 10.0.0.0/24 accept
sudo nft add rule inet filter input tcp dport 8470 drop
```

---

## CSV Export Hardening

The CSV export endpoints (`GET /api/v1/export/sessions` and `GET /api/v1/export/history`) produce RFC 4180-compliant CSV files with additional security hardening against spreadsheet formula injection.

### Formula Injection Prevention

Spreadsheet applications (Microsoft Excel, LibreOffice Calc, Google Sheets) interpret cell values beginning with certain characters as formulas or commands. An attacker who can influence session usernames or other fields could inject payloads like `=HYPERLINK("http://evil.com")` or `=cmd|'/C calc'!A0`.

DawOS Agent sanitises all CSV cell values before output:

| Character | Risk | Mitigation |
|-----------|------|------------|
| `=` | Formula execution | Prefixed with single-quote |
| `+` | Formula execution | Prefixed with single-quote |
| `-` | Formula execution (negative number ambiguity) | Prefixed with single-quote |
| `@` | External data reference | Prefixed with single-quote |
| `\t` (tab) | Field separator injection | Prefixed with single-quote |
| `\r` (carriage return) | Row injection | Prefixed with single-quote |

The sanitisation function checks only the first character of each value. A leading single-quote (`'`) neutralises the formula trigger in all major spreadsheet applications without altering the data for non-spreadsheet consumers (databases, scripts, log aggregators).

Additionally, all cell values are wrapped in double quotes via `csv.QUOTE_ALL`, which provides a secondary defense layer against delimiter injection.

### Export Size Limits

The history export endpoint clamps the `limit` parameter to the range `[1, 50000]` to prevent denial-of-service via excessively large database dumps. The default limit is 10,000 records.

---

## Session History Database Security

The session history feature stores snapshots of active PPPoE sessions in a local SQLite database. Several layers protect this data store.

### SQL Injection Prevention

All database queries use parameterised SQL with `?` placeholders. No user input is ever interpolated into SQL strings via f-strings, string concatenation, or `.format()`.

```python
# How queries are constructed (safe)
conn.execute(
    "DELETE FROM session_history WHERE snapshot_at < ?;",
    (before,),
)

# What is NOT done (unsafe)
conn.execute(f"DELETE FROM session_history WHERE snapshot_at < '{before}';")
```

This pattern applies to all five SQL operations: insert (snapshot), select (query), count (pagination), delete (purge), and aggregate (stats).

### Database Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DAWOS_HISTORY_DB` | `/var/lib/dawos-agent/history.db` | Filesystem path to the SQLite database file |

The database file is created automatically on first use. The parent directory is created if it does not exist. WAL (Write-Ahead Logging) mode is enabled for concurrent read performance.

### Access Control

| Endpoint | Auth Level | Rationale |
|----------|-----------|-----------|
| `GET /api/v1/sessions/history` | ViewerKey | Read-only query |
| `POST /api/v1/sessions/history/snapshot` | ViewerKey | Non-destructive capture |
| `DELETE /api/v1/sessions/history` | ApiKey | Destructive bulk delete |
| `GET /api/v1/sessions/history/stats` | ViewerKey | Read-only aggregate |

The purge endpoint requires ApiKey (operator/admin) authentication because it permanently deletes data.

---

## Config Validator Safety

The config validation endpoint (`POST /api/v1/config/validate`) accepts raw accel-ppp configuration text and returns a list of structural issues.

The validator is **inherently safe by design**:

- Pure Python implementation -- no shell commands, no subprocess calls
- No file system access -- does not read from or write to disk
- No network calls -- operates entirely in-memory
- No `eval()` or `exec()` -- uses only regex matching and string operations
- Input is treated as plain text data, never as executable code

The validator checks:

- Section header syntax (`[section-name]`)
- Key-value pair format
- IP address and CIDR notation validity
- Port number ranges (1-65535)
- Bare-key sections (`[modules]` and `[ip-pool]`)
- Duplicate section detection

Invalid input produces informational warnings rather than errors, making the endpoint safe for exploratory use.

---

## RADIUS Secret Protection

The RADIUS diagnostics endpoints (`GET /api/v1/radius/config`, `/status`, `/check`) provide visibility into RADIUS server configuration and connectivity without exposing sensitive credentials.

**Shared secrets are never returned to API callers.** The config parser regex intentionally captures only the server address and port fields from `server=`, `auth-server=`, and `acct-server=` directives. The shared secret (typically the second comma-separated field) is discarded during parsing.

This is enforced at the service layer (`services/radius.py`), not at the router layer, so there is no code path that could accidentally leak a secret through response serialisation.

---

## Dependency Security

All Python dependencies are audited for known vulnerabilities:

```bash
pip-audit
```

This check is part of the project's quality gates. New dependencies are only added after passing a `pip-audit` scan.

Current dependencies with security relevance:

| Package | Purpose | Why It Is Needed |
|---------|---------|-----------------|
| `fastapi` | Web framework | HTTP request handling |
| `uvicorn` | ASGI server | Production server |
| `pydantic` | Data validation | Input sanitization |
| `slowapi` | Rate limiting | Abuse prevention |
| `prometheus-client` | Metrics | Observability |
| `python-json-logger` | Structured logging | Audit trail |

---

## Security Checklist for Deployment

Before putting DawOS Agent into production:

1. Generate a strong API key (minimum 32 characters, `secrets.token_urlsafe`)
2. Set file permissions: `agent.env` as `0640 root:dawos`
3. Bind to management interface only (not `0.0.0.0`)
4. Deploy behind a TLS-terminating reverse proxy
5. Firewall port 8470 to authorized hosts only
6. Verify sudoers file is correct: `sudo visudo -cf /etc/sudoers.d/dawos-agent`
7. Enable rate limiting (default `120/minute` is a good starting point)
8. Set up RBAC if multiple teams access the agent
9. Enable webhook signing if using webhooks
10. Set `DAWOS_LOG_FORMAT=json` for machine-parseable audit logs
11. Run `pip-audit` to verify no known vulnerabilities
12. Review `journalctl -u dawos-agent` for any startup warnings
