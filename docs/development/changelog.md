# Changelog

All notable changes to dawos-agent are documented here. For the full changelog with detailed descriptions, see [CHANGELOG.md on GitHub](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/CHANGELOG.md).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/).

---

## Unreleased

### Added

- `GET /api/v1/network/throughput` — read-only endpoint (ViewerKey) that reads `/proc/net/dev` and returns aggregate plus per-interface cumulative `rx_bytes` / `tx_bytes` counters. No sudo required.
- `POST /api/v1/conntrack/flush` — operator endpoint (ApiKey) that runs `conntrack -F` via sudo to clear all nf_conntrack entries. Returns pre-flush entry count. Sudoers entry added for `/usr/sbin/conntrack`.

### Changed

- Bulk endpoint docstrings now include request body JSON examples — documents that `BulkRateLimitRequest` uses per-item objects (`{"items": [{"username": "...", "rate": "..."}]}`) rather than a flat usernames+rate shape.
- Test suite: 1144 tests, 100% coverage maintained

### Fixed

- `sessions/stats` returns numeric fields as numbers — `SessionStatsResponse` now types `cpu_percent` as `float` and `pool_used`/`pool_total` as `int` instead of `str`
- SNMP health check: replaced UDP socket probe with `ss -lun` for reliability
- IP pool CIDR validation returns HTTP 422 instead of 409
- `restart_session()` catches `RuntimeError` and reports `success: false`
- Event handler webhooks now fire actual HTTP POST via `httpx.AsyncClient`
- Event history bounded to 1000 entries via `deque(maxlen=1000)`
- `parse_stat()` handles malformed accel-cmd output gracefully
- Renamed misleading `cache_size` variable

### Security

- Internal error details no longer leaked to API clients (27 router modules, 106 handlers)
- `X-Request-ID` header validated against printable ASCII regex before acceptance
- WebSocket `/ws/events` now prefers `X-API-Key` header over query parameter

---

## v0.3.2 (2026-07-09)

### Added

- Graceful shutdown endpoints for controlled accel-ppp daemon shutdown:
    - `POST /api/v1/service/shutdown` — soft (drain) or hard (immediate) mode with `confirm` safety guard
    - `POST /api/v1/service/shutdown/cancel` — cancel a pending soft shutdown and resume normal operation
- `ShutdownMode` enum, `ShutdownRequest`, and `ShutdownResponse` Pydantic models
- `shutdown(mode)` and `shutdown_cancel()` async service functions

---

## v0.3.1 (2026-07-09)

### Fixed

- Version reporting -- `/health` endpoint and `__version__` now read from package metadata via `importlib.metadata.version()` instead of a hardcoded string. Single source of truth is `pyproject.toml`.
- httpx missing from main dependencies -- `POST /api/v1/service/command` returned HTTP 500 on fresh installs (BUG-8)
- Health readiness probe accel-cmd flags -- `-H` accepts host only; port needs separate `-p` flag (BUG-9)
- Pylint R0903 false positives on middleware/logging dataclasses

---

## v0.3.0 (2026-07-09)

### Added

- WebSocket event bus with 4 channels (session, config, audit, system) for real-time streaming
- Prometheus metrics endpoint (`GET /metrics`) with 5 application metrics
- Health readiness probe (`GET /health/ready`) for load balancer integration
- Request ID middleware (UUID v4 in `X-Request-ID` response header)
- Rate limiting (per-IP, default 120/minute, configurable)
- Structured JSON logging (opt-in via `DAWOS_LOG_FORMAT=json`)
- Retry with exponential backoff for transient accel-cmd failures
- RBAC with three tiers: viewer, operator, admin
- Audit log with in-memory ring buffer and admin-only query endpoint
- Webhook notifications with optional HMAC-SHA256 signing
- Bulk operations endpoint for batch API calls
- Operational playbooks (health-check, backup-config, safe-restart)
- Comprehensive input validation with regex patterns and `shlex.quote()` defense-in-depth
- Metrics middleware (pure ASGI, excludes health/metrics paths)
- Named constants extracted to `dawos_agent/constants.py`

### Changed

- Systemd unit hardened: `Restart=always`, `WatchdogSec=30`, `StartLimitBurst=5/300s`
- Installer inline systemd unit synchronized with main unit file

### Fixed

- Installer now sets ownership of `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/` to `dawos` user
- Installer `ReadWritePaths` synced with main unit (added resolved.conf.d, dnsmasq.d, dnsmasq.conf)

### Documentation

- Monitoring Integration guide (Prometheus, Grafana, alerting, WebSocket, audit)
- Production Hardening guide (resources, log rotation, systemd, scaling, backup)
- Architecture Decision Records (14 ADRs)
- Comprehensive security documentation

---

## v0.2.0 (2026-07-08)

### Changed

- All 14 DELETE endpoints standardized to HTTP 204 No Content (previously 12 of 14 returned 200 with JSON body)

### Added

- Live integration test report -- 106 endpoints tested against real BNG node
- Config content validation (`field_validator` + `min_length=10`) to reject empty config writes
- GitHub Actions CI, Release, and Docs workflows
- Pre-commit hooks (Black, Ruff, Pylint)
- MkDocs Material documentation site

### Fixed

- DNS write permissions -- `set_dns()` now uses `sudo tee` for root-owned `/etc/resolv.conf`
- DNS systemd sandbox -- added `/etc/resolv.conf` to `ReadWritePaths`
- Empty config protection -- `PUT /api/v1/config` with empty content now returns HTTP 422
- 32 Ruff lint violations fixed (SIM103, SIM105, SIM117, E501, F841)
- Inline comments removed from accel-ppp config template (caused `pppd_compat` path errors)
- Safety-net `_ensure_accel_service` call added in installer

---

## v0.1.0 (2026-07-06)

Initial release.

### Added

- PPP router management agent with 138 API endpoints across 29 router modules
- 28 service modules covering sessions, config, network, firewall, NAT, PPPoE, traffic, routing, conntrack, IP pools, DHCP, DNS, NTP, LLDP, VRRP, monitoring, diagnostics, flow accounting, event handling, zone firewall, scheduler, connection limits, MAC filtering, PADO delay, and logs
- X-API-Key authentication with 401 responses
- Pydantic v2 request/response models (140+ schemas)
- Guarded config apply with auto-revert (checkpoint system)
- SSE streaming for traffic monitoring and log tailing
- Interactive installer with TUI wizard (`install.sh` v2.0)
- Non-interactive install mode (`--yes` flag) and uninstaller (`--uninstall`)
- Systemd service with security hardening
- Sudoers configuration with least-privilege rules (6 commands only)
