# Security Policy

See the full security policy on GitHub: [SECURITY.md](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/SECURITY.md)

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it privately via GitHub Security Advisories or email. **Do not open a public issue.**

## Security Measures

### Authentication

- All API endpoints (except `/health`) require an `X-API-Key` header.
- Invalid or missing keys return **HTTP 401 Unauthorized**.
- API keys should be strong, randomly generated secrets (43+ characters).

### Systemd Sandboxing

The service runs with strict systemd hardening:

| Directive | Value | Effect |
|-----------|-------|--------|
| `ProtectSystem` | `strict` | Filesystem read-only except whitelisted paths |
| `ProtectHome` | `true` | `/home`, `/root`, `/run/user` inaccessible |
| `PrivateTmp` | `true` | Isolated `/tmp` directory |
| `NoNewPrivileges` | `false` | Required for sudo escalation |

### Least-Privilege Sudo

Only 6 specific commands are allowed via passwordless sudo:

| Command | Purpose |
|---------|---------|
| `nft` | Firewall and NAT rules |
| `ip` | Network interfaces and routes |
| `tc` | Traffic shaping / QoS |
| `vtysh` | FRR routing daemon |
| `sysctl` | Kernel parameter tuning |
| `tee` | Config file writes |

No shell access, no wildcards, no unrestricted commands.

### Code Safety

- **No `eval()` or `exec()`** anywhere in the codebase.
- **No `shell=True`** -- all subprocess calls use list-form arguments.
- **No string interpolation** in shell commands.
- **pip-audit** clean -- zero known vulnerabilities in dependencies.

### Network

- Default: listens on `0.0.0.0:8470` (all interfaces).
- Production: bind to management interface only (`DAWOS_HOST=10.0.0.1`).
- TLS: deploy behind nginx/Caddy reverse proxy for HTTPS.

### File Permissions

| File | Mode | Owner | Contains |
|------|------|-------|----------|
| `/etc/dawos-agent/agent.env` | `0640` | `root:dawos` | API key |
| `/etc/sudoers.d/dawos-agent` | `0440` | `root:root` | Sudo rules |
