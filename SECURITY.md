# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

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

## Security Considerations

### Authentication

- All API endpoints require an `X-API-Key` header.
- Missing or invalid keys receive a **401 Unauthorized** response.
- Always use **strong, randomly generated** API keys (minimum 32 characters).

### File Permissions

- The configuration file (`/etc/dawos-agent/config.ini`) should be owned by
  `root:dawos` with mode **0640**.
- The API key is stored in this file — restrict read access accordingly.

### Sudoers (Least Privilege)

The dawos-agent service account is granted sudo access **only** for the
specific commands it needs:

- `nft` — nftables firewall management
- `ip` — network interface and routing management
- `tc` — traffic control
- `vtysh` — FRRouting CLI access
- `sysctl` — kernel parameter tuning
- `tee` — writing to system files

No blanket `NOPASSWD: ALL` is used. Each command is explicitly listed in the
sudoers configuration.

### Systemd Hardening

The systemd service unit includes the following security directives:

- `ProtectSystem=strict` — mounts the filesystem as read-only
- `ProtectHome=yes` — hides home directories
- `PrivateTmp=yes` — isolates temporary files
- `NoNewPrivileges=yes` — prevents privilege escalation
- `ProtectKernelModules=yes` — blocks module loading
- `ProtectKernelTunables=yes` — blocks sysctl writes (except via allowed sudo)

### Subprocess Safety

- **No shell injection**: all subprocess calls use **list-form arguments**
  (e.g., `["ip", "addr", "show"]`), never string interpolation into shell
  commands.
- **No `eval()` or `exec()`** anywhere in the codebase.
- **No `shell=True`** in any subprocess call.

### Dependency Security

- **pip-audit clean** — zero known vulnerabilities in all dependencies.
- Dependencies are pinned and regularly audited.

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

1. **Change the default API key** — generate a cryptographically random key:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use TLS** — place dawos-agent behind a reverse proxy (e.g., nginx) with
   TLS termination. Never expose the API over plain HTTP in production.

3. **Restrict the listen address** — bind to `127.0.0.1` or a management
   network interface, not `0.0.0.0`.

4. **Firewall the agent port** — allow access only from authorized management
   hosts.

5. **Keep the system updated** — apply security patches to the OS, Python, and
   dawos-agent regularly.

6. **Monitor access logs** — review dawos-agent and reverse proxy logs for
   unauthorized access attempts.

7. **Use a dedicated service account** — never run dawos-agent as root. The
   installer creates a dedicated `dawos` user with minimal permissions.
