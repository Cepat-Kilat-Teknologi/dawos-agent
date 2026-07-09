# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Please report vulnerabilities by email to:

**security@cepat-kilat.id**

Include the following in your report:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

| Action | Timeline |
|--------|----------|
| Acknowledge receipt | Within **48 hours** |
| Initial assessment | Within **5 business days** |
| Fix development | Depends on severity |
| Security advisory | Published with the fix release |

We will keep you informed of progress toward a fix and full announcement. We may
ask for additional information or guidance during the process.

## Security Architecture

### Authentication

- All API endpoints (except `/health`, `/health/ready`, and `/metrics`) require an `X-API-Key` header.
- Missing or invalid keys receive a **401 Unauthorized** response.
- Always use **strong, randomly generated** API keys (minimum 32 characters).
- The WebSocket endpoint at `/ws/events` accepts the key as a `key` query parameter.

### Role-Based Access Control (RBAC)

DawOS Agent supports three access tiers:

| Role | Access Level | Typical Use |
|------|-------------|-------------|
| viewer | GET endpoints only | Monitoring dashboards, read-only scripts |
| operator | GET + POST/PUT/DELETE | Day-to-day management operations |
| admin | Full access including audit, playbooks, service restart | Infrastructure administration |

The primary `DAWOS_API_KEY` always grants admin access. For multi-key RBAC, configure `DAWOS_API_KEYS_FILE` with a JSON file mapping keys to roles:

```json
{
  "key-for-monitoring": "viewer",
  "key-for-noc-team": "operator",
  "key-for-infra-admin": "admin"
}
```

### Rate Limiting

- Per-IP rate limiting via SlowAPI. Default: `120/minute`.
- Configurable via `DAWOS_RATE_LIMIT` environment variable.
- Health, readiness, and metrics endpoints are exempt.
- Returns HTTP 429 with `Retry-After` header when triggered.
- Rate limit hits are tracked by the `dawos_rate_limit_hits_total` Prometheus counter.

### Webhook Signing

When `DAWOS_WEBHOOK_SECRET` is configured, all outbound webhook payloads are signed with HMAC-SHA256. The signature is sent in the `X-Dawos-Signature` header. Consumers should verify the signature before processing the payload.

### File Permissions

| File | Mode | Owner | Contains |
|------|------|-------|----------|
| `/etc/dawos-agent/agent.env` | `0640` | `root:dawos` | API key, configuration |
| `/etc/sudoers.d/dawos-agent` | `0440` | `root:root` | Sudo rules |
| `/etc/accel-ppp.conf` | owned by `dawos` | `dawos:dawos` | accel-ppp configuration |
| `/etc/accel-ppp.d/` | owned by `dawos` | `dawos:dawos` | accel-ppp config fragments |

The installer sets ownership of `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/` to the `dawos` service user. This is required for config checkpoint and rollback operations.

### Sudoers (Least Privilege)

The DawOS Agent service account is granted sudo access **only** for the
specific commands it needs:

| Command | Purpose |
|---------|---------|
| `nft` | nftables firewall management |
| `ip` | Network interface and routing management |
| `tc` | Traffic control / QoS |
| `vtysh` | FRRouting CLI access |
| `sysctl` | Kernel parameter tuning |
| `tee` | Writing to system files |

No blanket `NOPASSWD: ALL` is used. Each command is explicitly listed in the
sudoers configuration. No shell access, no wildcards, no unrestricted commands.

### Systemd Hardening

The systemd service unit includes the following security directives:

| Directive | Value | Effect |
|-----------|-------|--------|
| `ProtectSystem` | `strict` | Filesystem read-only except whitelisted paths |
| `ProtectHome` | `true` | `/home`, `/root`, `/run/user` inaccessible |
| `PrivateTmp` | `true` | Isolated `/tmp` directory |
| `NoNewPrivileges` | `false` | Required for sudo escalation to work |
| `Restart` | `always` | Restarts on any exit (crash, clean exit, signal) |
| `WatchdogSec` | `30` | Kills process if hung for 30 seconds |
| `StartLimitBurst` | `5` | Max 5 restarts per interval |
| `StartLimitIntervalSec` | `300` | 5-minute restart window |

Only explicitly listed paths in `ReadWritePaths` are writable. All other filesystem locations are read-only.

### Subprocess Safety

- **No shell injection**: all subprocess calls use **list-form arguments**
  (e.g., `["ip", "addr", "show"]`), never string interpolation into shell
  commands.
- **Defense-in-depth**: `shlex.quote()` applied on user-supplied values in 5
  service modules as an additional layer.
- **No `eval()` or `exec()`** anywhere in the codebase.
- **No `shell=True`** in any subprocess call.

### Dependency Security

- **pip-audit clean** -- zero known vulnerabilities in all dependencies.
- Dependencies are regularly audited.

### Network Isolation

- Default: listens on `0.0.0.0:8470` (all interfaces).
- Production: bind to management interface only (`DAWOS_HOST=10.0.0.1` or `127.0.0.1`).
- TLS: deploy behind nginx or Caddy reverse proxy for HTTPS termination.
- Firewall the agent port -- allow access only from authorized management hosts.

## Responsible Disclosure

We kindly ask that you:

1. **Allow us reasonable time** to investigate and address the issue before
   public disclosure.
2. **Make a good-faith effort** to avoid privacy violations, data destruction,
   and service disruption during your research.
3. **Do not exploit** the vulnerability beyond what is necessary to demonstrate
   the issue.

We will credit reporters in the security advisory (unless you prefer to remain
anonymous).

## Security Best Practices for Deployment

1. **Change the default API key** -- generate a cryptographically random key:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use TLS** -- place DawOS Agent behind a reverse proxy (e.g., nginx) with
   TLS termination. Never expose the API over plain HTTP in production.

3. **Restrict the listen address** -- bind to `127.0.0.1` or a management
   network interface, not `0.0.0.0`.

4. **Firewall the agent port** -- allow access only from authorized management
   hosts.

5. **Enable rate limiting** -- keep the default `120/minute` or adjust to your
   traffic patterns.

6. **Use RBAC** -- assign viewer/operator roles to limit blast radius of
   compromised keys.

7. **Enable webhook signing** -- set `DAWOS_WEBHOOK_SECRET` to verify webhook
   payload integrity.

8. **Keep the system updated** -- apply security patches to the OS, Python, and
   dawos-agent regularly.

9. **Monitor access logs** -- review DawOS Agent audit log and reverse proxy
   logs for unauthorized access attempts.

10. **Use a dedicated service account** -- never run DawOS Agent as root. The
    installer creates a dedicated `dawos` user with minimal permissions.
