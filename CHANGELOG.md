# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Request ID middleware** -- Every HTTP request is assigned a UUID v4 trace ID, returned in the `X-Request-ID` response header. Client-supplied `X-Request-ID` values are preserved. The trace ID is injected into all log records for end-to-end request tracing.
- **Health readiness probe** -- New `GET /health/ready` endpoint checks accel-ppp connectivity and returns HTTP 200 (all dependencies reachable) or HTTP 503 (dependency down). The existing `/health` endpoint remains a lightweight liveness check.
- **Rate limiting** -- Global per-IP rate limiting via slowapi. Default: 120 requests/minute per IP. Configurable via `DAWOS_RATE_LIMIT` environment variable. Health endpoints are exempt. Set to empty string to disable.
- **Structured JSON logging** -- Opt-in JSON log format via `DAWOS_LOG_FORMAT=json`. Each log line is a valid JSON object with `timestamp`, `level`, `name`, `message`, and `request_id` fields. Default remains human-readable text format.
- **Configurable ping target** -- Internet reachability diagnostic check now uses `DAWOS_PING_TARGET` (default: `8.8.8.8`). Override for air-gapped networks or custom DNS.
- **PEP 561 type marker** -- Added `py.typed` marker file for downstream type-checking support.
- **Named constants** -- Extracted magic numbers to `dawos_agent/constants.py` (shared) and module-level constants (local). Improves readability and single-source-of-truth for conntrack thresholds, port numbers, and byte conversion factors.
- **Comprehensive input validation** -- All request models now validate user-supplied fields against regex patterns and type constraints at the Pydantic layer (HTTP 422 rejection). Covers 30+ fields across session, network, firewall, NAT, PPPoE, conntrack, DNS, routing, zone, VRRP, scheduler, event, IP pool, and monitoring endpoints.
- **Shell injection defense-in-depth** -- Added `shlex.quote()` wrapping in 5 service modules (`accel.py`, `monitoring.py`, `zone_firewall.py`, `firewall_groups.py`, `network.py`) for all user-supplied values interpolated into shell commands.
- **Input validation reference** -- New documentation page (`docs/api/validation-rules.md`) with per-endpoint field constraints, regex patterns, and shell quoting details.
- **Validation tests** -- 17 new unit tests covering regex rejection, list field validation, and service-level error paths.
- **New dependencies** -- `slowapi>=0.1.9,<1` (rate limiting), `python-json-logger>=3,<5` (structured logging). Both pip-audit clean.

### Changed

- **API reference updated** -- Common Patterns section now documents HTTP 422 validation errors, rate limiting (HTTP 429), request tracing (X-Request-ID), and readiness probe usage.
- **Configuration documentation updated** -- New settings reference sections for `DAWOS_LOG_FORMAT`, `DAWOS_PING_TARGET`, and `DAWOS_RATE_LIMIT`. Logging section expanded with JSON format examples and request tracing guide.

### Removed

- **Dead code cleanup** -- Removed unused `TrafficSample` and `ClearHistoryResponse` models from `schemas.py`.

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

[Unreleased]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases/tag/v0.2.0
[0.1.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases/tag/v0.1.0
