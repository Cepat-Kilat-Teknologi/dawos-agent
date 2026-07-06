# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-07-06

### Added

- Initial release of dawos-agent.
- PPP router management agent.
- 128+ API endpoints across 27 router modules.
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

[Unreleased]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases/tag/v0.1.0
