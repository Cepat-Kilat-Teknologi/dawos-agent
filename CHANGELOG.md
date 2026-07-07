# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases/tag/v0.1.0
