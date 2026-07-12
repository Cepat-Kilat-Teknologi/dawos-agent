# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.3] - 2026-07-12

### Added

- **`GET /api/v1/network/throughput`** -- read-only endpoint (ViewerKey) that
  reads `/proc/net/dev` and returns aggregate plus per-interface cumulative
  `rx_bytes` / `tx_bytes` counters.  `rx_bps` / `tx_bps` are always `0` on a
  single snapshot; callers compute rate from two successive reads.  No sudo
  required.

- **`POST /api/v1/conntrack/flush`** -- operator endpoint (ApiKey) that runs
  `conntrack -F` via sudo to clear all nf_conntrack entries.  Returns
  pre-flush entry count.  Sudoers entry added for `/usr/sbin/conntrack`.

### Changed

- **bulk endpoint docstrings now include request body JSON examples** --
  module docstring and per-endpoint docstrings for `/api/v1/bulk/terminate`,
  `/ratelimit`, and `/shaper-restore` now show the exact wire format.
  Documents that `BulkRateLimitRequest` uses per-item objects
  (`{"items": [{"username": "...", "rate": "..."}]}`) rather than a flat
  usernames+rate shape.
- **Test suite expanded** -- 1144 tests (up from 1133), 100% coverage
  maintained. New tests cover throughput, conntrack flush, session restart
  failure path, and IP pool CIDR validation error codes.

### Fixed

- **sessions/stats returns numeric fields as numbers** -- `SessionStatsResponse`
  now types `cpu_percent` as `float` and `pool_used`/`pool_total` as `int`
  instead of `str`.  JSON consumers receive proper numeric values (e.g.
  `"cpu_percent": 3.0`) rather than numeric-strings (`"cpu_percent": "3"`).
  Pydantic v2 coercion handles the conversion transparently from the existing
  string-returning parsers.
- **SNMP health check reliability** -- Replaced unreliable UDP socket probe
  (`socket.sendto` to port 161) with `ss -lun sport = :161` to verify SNMP
  daemon is actually listening. The socket probe returned false positives when
  the kernel accepted the datagram into a buffer even though no SNMP daemon was
  running.
- **IP pool CIDR validation returns HTTP 422** -- `POST /api/v1/ip-pool` with
  an invalid CIDR range now returns HTTP 422 (Unprocessable Entity) instead of
  HTTP 409 (Conflict). Duplicate pool names still return 409. The error code is
  selected based on the `ValueError` message content.
- **Session restart reports terminate failures** -- `restart_session()` now
  catches `RuntimeError` from `accel.terminate_session()` and returns
  `{"success": false}` with a descriptive message instead of silently reporting
  success when the terminate step fails.
- **Event handler webhook execution** -- `fire_event()` now sends actual HTTP
  POST requests to webhook URLs via `httpx.AsyncClient` instead of simulating
  success without network activity. The response status code is captured and
  `success` is set based on whether the status is below 400.
- **Event history bounded** -- The in-memory event log is now backed by
  `collections.deque(maxlen=1000)` to prevent unbounded memory growth on
  long-running agent instances. Oldest entries are automatically evicted when
  the buffer is full.
- **parse_stat ValueError protection** -- `accel.parse_stat()` now handles
  malformed output from `accel-cmd show stat` gracefully instead of raising
  an unhandled `ValueError`.
- **Misleading variable name** -- Renamed internal `cache_size` variable to
  accurately reflect its purpose, improving code readability.

### Security

- **Internal error details no longer leaked to API clients** -- All 27 router
  modules now return a generic `"Internal server error"` message for HTTP 500
  responses instead of forwarding raw exception text (`str(exc)`). Client-facing
  4xx errors (400, 404, 409) retain descriptive messages since those contain
  controlled, non-sensitive text. 106 error handlers updated across the codebase.
- **X-Request-ID header validated** -- Caller-supplied `X-Request-ID` values are
  now validated against `[\x20-\x7E]{1,128}` (printable ASCII, max 128 chars).
  Invalid or missing values are replaced with a generated UUID v4. Prevents
  header injection and log pollution from malformed trace IDs.
- **WebSocket authentication prefers header over query parameter** -- The
  `/ws/events` endpoint now checks the `X-API-Key` header first and falls back
  to the `key` query parameter only when the header is absent. This reduces the
  risk of API key exposure in server access logs and browser history.

## [0.3.2] - 2026-07-09

### Added

- **Graceful shutdown endpoints** -- Two new admin-only endpoints for controlled accel-ppp daemon shutdown:
  - `POST /api/v1/service/shutdown` — Initiate soft (drain) or hard (immediate) shutdown. Soft mode stops accepting new PPPoE connections while keeping all existing sessions alive; the daemon exits only after every session disconnects naturally. Hard mode drops all sessions and exits immediately. Requires `"confirm": true` in the request body as a safety guard against accidental invocation. Reports the number of active sessions at request time.
  - `POST /api/v1/service/shutdown/cancel` — Cancel a pending soft shutdown and resume accepting new connections. Has no effect if no soft shutdown is in progress.
- **Shutdown models** -- `ShutdownMode` enum (`soft`/`hard`), `ShutdownRequest` (with confirm safety flag), and `ShutdownResponse` Pydantic models.
- **Shutdown service functions** -- `shutdown(mode)` and `shutdown_cancel()` async functions wrapping `accel-cmd shutdown` with `shlex.quote()` input sanitisation.

## [0.3.1] - 2026-07-09

### Fixed

- **Version reporting** -- Health endpoint and `__version__` now read from package metadata via `importlib.metadata.version()` instead of a hardcoded string. Previously, bumping `pyproject.toml` without updating `__init__.py` caused `/health` to report stale version numbers. Single source of truth is now `pyproject.toml`.

## [0.3.0] - 2026-07-09

### Added

- **WebSocket event bus** -- Real-time event streaming via `WS /ws/events` with API key authentication (query parameter). Four channels: `session`, `config`, `audit`, `system`. Per-subscriber `asyncio.Queue` with configurable max size prevents slow consumers from blocking publishers. Supports `subscribe`, `unsubscribe`, and `ping` control messages.
- **Prometheus metrics endpoint** -- `GET /metrics` exposes application metrics in Prometheus text exposition format. Five metrics: `dawos_http_requests_total` (counter), `dawos_http_request_duration_seconds` (histogram), `dawos_accel_cmd_errors_total` (counter), `dawos_accel_cmd_retries_total` (counter), `dawos_rate_limit_hits_total` (counter). No authentication required. Rate limiting exempt.
- **Metrics middleware** -- Pure ASGI middleware (not `BaseHTTPMiddleware`) records HTTP request metrics. Health, metrics, and readiness paths excluded from recording to prevent self-instrumentation loops.
- **Request ID middleware** -- Every HTTP request receives a UUID v4 trace ID in the `X-Request-ID` response header. Client-supplied values are preserved for distributed tracing. The ID is injected into all log records.
- **Health readiness probe** -- `GET /health/ready` checks accel-ppp connectivity and returns HTTP 200 or HTTP 503. The existing `/health` remains a lightweight liveness check.
- **Rate limiting** -- Per-IP rate limiting via SlowAPI. Default: `120/minute`. Configurable via `DAWOS_RATE_LIMIT`. Health and metrics endpoints exempt. Returns HTTP 429 with `Retry-After` header when triggered.
- **Structured JSON logging** -- Opt-in via `DAWOS_LOG_FORMAT=json`. Each log line is a valid JSON object with `timestamp`, `level`, `name`, `message`, and `request_id` fields. Default remains human-readable text format.
- **Retry with exponential backoff** -- `accel-cmd` calls retry on transient failures with configurable `DAWOS_RETRY_MAX` (default 3) and `DAWOS_RETRY_DELAY` (default 1.0s). Non-transient errors propagate immediately. Retry count tracked by Prometheus counter.
- **RBAC (Role-Based Access Control)** -- Three-tier role hierarchy: viewer (read-only), operator (read+write), admin (full access). Configure via `DAWOS_API_KEYS_FILE` (JSON key-to-role mapping). Single-key mode backward compatible -- `DAWOS_API_KEY` grants admin access.
- **Audit log** -- All mutating requests logged to `dawos_agent.audit` with method, path, client IP, request ID, RBAC role, status code, and duration. In-memory ring buffer (`DAWOS_AUDIT_BUFFER_SIZE`, default 1000) exposed via admin-only `GET /api/v1/audit` with filtering.
- **Webhook notifications** -- Fire-and-forget HTTP POST on every mutating request. Enable via `DAWOS_WEBHOOK_URL`. Optional HMAC-SHA256 signing via `DAWOS_WEBHOOK_SECRET` (sent in `X-Dawos-Signature` header). Non-blocking delivery.
- **Bulk operations** -- `POST /api/v1/bulk` accepts multiple API calls in a single request for batch processing. Operator role required.
- **Operational playbooks** -- `GET /api/v1/playbooks` and `POST /api/v1/playbooks/{name}/run`. Three built-in sequences: `health-check`, `backup-config`, `safe-restart`. Admin role required.
- **Comprehensive input validation** -- All request models validate fields with regex patterns and type constraints at the Pydantic layer (HTTP 422). Covers 30+ fields with `shlex.quote()` defense-in-depth in 5 service modules.
- **Config completeness check** -- Startup warnings for insecure default API key and unconfigured optional settings.
- **Named constants** -- Extracted magic numbers to `dawos_agent/constants.py` for readability and single-source-of-truth.
- **PEP 561 type marker** -- `py.typed` marker for downstream type-checking.
- **New dependencies** -- `prometheus-client>=0.20,<1`, `slowapi>=0.1.9,<1`, `python-json-logger>=3,<5`. All pip-audit clean.

### Changed

- **API reference updated** -- Common Patterns section documents HTTP 422 validation errors, rate limiting (HTTP 429), request tracing (X-Request-ID), WebSocket protocol, and readiness probe usage.
- **Configuration documentation updated** -- New settings reference for `DAWOS_LOG_FORMAT`, `DAWOS_PING_TARGET`, `DAWOS_RATE_LIMIT`, `DAWOS_RETRY_MAX`, `DAWOS_RETRY_DELAY`, `DAWOS_AUDIT_BUFFER_SIZE`, `DAWOS_WEBHOOK_URL`, `DAWOS_WEBHOOK_SECRET`, and `DAWOS_API_KEYS_FILE`.
- **Systemd unit hardened** -- `Restart=on-failure` changed to `Restart=always` to handle clean exits from uncaught exceptions. Added `WatchdogSec=30` for hung process detection. `StartLimitBurst` increased from 3 to 5 with interval extended from 60s to 300s. `RestartSec` reduced from 5s to 3s.
- **Installer inline systemd unit** -- Synchronized with the main unit file to include all hardening directives.

### Fixed

- **Installer: accel-ppp config ownership** -- The installer now sets ownership of `/etc/accel-ppp.conf` and `/etc/accel-ppp.d/` to the `dawos` service user after package installation. Without this, config checkpoint and rollback operations fail with HTTP 500 on fresh installs.
- **Installer: ReadWritePaths sync** -- The inline systemd unit fallback now includes `/etc/systemd/resolved.conf.d`, `/etc/dnsmasq.d`, and `/etc/dnsmasq.conf` in `ReadWritePaths`, matching the main unit file.
- **httpx missing from main dependencies** -- `POST /api/v1/service/command` returned HTTP 500 (`ModuleNotFoundError: httpx`) on fresh installs because `httpx` was listed only in dev dependencies. Moved to main `dependencies` in `pyproject.toml`. (BUG-8)
- **Health readiness probe accel-cmd flags** -- `GET /health/ready` returned HTTP 503 even when accel-ppp was running. The `-H` flag accepts host only; port requires a separate `-p` flag. Changed from `-H 127.0.0.1:2001` to `-H 127.0.0.1 -p 2001`. (BUG-9)
- **Pylint R0903 false positives** -- Disabled `too-few-public-methods` globally for middleware and logging dataclasses that intentionally have few methods.

### Removed

- **Dead code cleanup** -- Removed unused `TrafficSample` and `ClearHistoryResponse` models from `schemas.py`.

### Documentation

- **Monitoring Integration guide** -- Prometheus scrape configurations (single-node, multi-node, service discovery), Grafana PromQL panels, 5 alerting rules, health probe configurations (Kubernetes, HAProxy, Nginx), WebSocket client examples (Python, JavaScript), audit log aggregation (Filebeat, Promtail), and environment variable reference.
- **Production Hardening guide** -- Resource planning with measured data, journald log rotation, swap configuration, systemd restart hardening, health check scripting, multi-node scaling architecture, security hardening, backup strategy, and 10-point post-hardening checklist.
- **Architecture Decision Records** -- 14 ADRs documenting key design decisions: FastAPI selection, router-service-shell architecture, API key auth with RBAC, Prometheus metrics, pure ASGI middleware, in-memory audit buffer, webhook delivery, WebSocket event bus, rate limiting, retry backoff, DELETE 204 convention, least-privilege sudoers, structured logging, and config checkpoint/rollback.

## [0.2.0] - 2026-07-08

### Changed

- **DELETE endpoints standardized to 204 No Content** — All 14 DELETE endpoints now return HTTP 204 with no response body on success, following REST best practices. Previously only 2 of 14 used 204; the remaining 12 returned 200 with JSON body. Affected endpoints: firewall groups, NAT masquerade, NAT egress, NAT public IP, IP pools, VLANs, routes, PPPoE interfaces, MAC filter, traffic ratelimit, zones, event history.

### Added

- **Live integration test report** — 106 endpoints tested against real BNG node (`docs/testing/test-report.md`)
- **Config content validation** — `field_validator` + `min_length=10` on `ConfigUpdateRequest` and `GuardedApplyRequest` to reject empty or malformed config writes
- **Unit tests** — 2 new tests for config content validation (824 total, 100% coverage)

### Fixed

- **DNS write permissions** — `set_dns()` now uses `sudo tee` subprocess instead of `path.write_text()` to handle root-owned `/etc/resolv.conf` and systemd-resolved symlinks
- **DNS systemd sandbox** — Added `/etc/resolv.conf` to `ReadWritePaths` in systemd unit and installer
- **Empty config protection** — `PUT /api/v1/config` with empty content previously wrote 0 bytes to `/etc/accel-ppp.conf`, destroying the configuration; now returns HTTP 422 with validation error

### Added

- **GitHub Actions CI** -- Automated lint + test pipeline on push and pull requests (`.github/workflows/ci.yml`)
- **GitHub Actions Release** -- PyPI publish + [GitHub Releases](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases) on version tag (`.github/workflows/release.yml`)
- **GitHub Actions Docs** -- MkDocs Material documentation site auto-deploy (`.github/workflows/docs.yml`)
- **Pre-commit hooks** -- Black, Ruff, and Pylint run automatically on `git commit` (`.pre-commit-config.yaml`)
- **MkDocs Material documentation** -- Full documentation site at [cepat-kilat-teknologi.github.io/dawos-agent](https://cepat-kilat-teknologi.github.io/dawos-agent/) (`docs/`, `mkdocs.yml`)

### Fixed

- Fix 32 Ruff lint violations (SIM103, SIM105, SIM117, E501, F841 across source and test files)
- Remove inline `#` comments from accel-ppp config template that caused
  `pppd_compat` path errors at startup (accel-ppp parser treats inline
  comments as part of the value string).
- Add safety-net `_ensure_accel_service` call in installer `main()` flow
  to guarantee the accel-ppp systemd unit is always created.

### Changed

- Update documentation with minimum hardware requirements and measured
  resource usage (CPU, RAM, disk).
- Update endpoint count to 138 across 29 API groups.
- Add accel-ppp build-from-source documentation and troubleshooting tips.
- README updated with PyPI install, badges, and docs URL.

## [0.1.0] - 2026-07-06

### Added

- Initial release of dawos-agent.
- PPP router management agent.
- 138 API endpoints across 29 router modules.
- 28 service modules covering: sessions, config, network, firewall, NAT, PPPoE,
  traffic, routing (BGP/OSPF/RIP/BFD), conntrack, IP pools, DHCP, DNS, NTP,
  LLDP, VRRP, monitoring, diagnostics, flow accounting, event handling, zone
  firewall, scheduler, connection limits, MAC filtering, PADO delay, and logs.
- X-API-Key authentication with 401 responses.
- Pydantic v2 request/response models (140+ schemas).
- Guarded config apply with auto-revert (checkpoint system).
- SSE streaming for traffic monitoring and log tailing.
- Interactive installer with TUI wizard (`install.sh` v2.0).
- Non-interactive install mode (`--yes` flag).
- Uninstaller (`--uninstall` flag).
- Systemd service with security hardening.
- Sudoers configuration with least-privilege rules.
- 808 tests with 100% code coverage.
- pylint 10.00/10 score.
- Black formatted codebase.
- Zero known vulnerabilities (pip-audit clean).
- Professional English docstrings on all public APIs.

[Unreleased]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases/tag/v0.2.0
[0.1.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases/tag/v0.1.0
