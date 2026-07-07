# Changelog

See the full changelog on GitHub: [CHANGELOG.md](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/CHANGELOG.md)

## v0.1.0 (2026-07-06)

Initial release.

### Added

- PPP router management agent with 138 API endpoints across 29 router modules.
- 28 service modules covering: sessions, config, network, firewall, NAT, PPPoE,
  traffic, routing (BGP/OSPF/RIP/BFD), conntrack, IP pools, DHCP, DNS, NTP,
  LLDP, VRRP, monitoring, diagnostics, flow accounting, event handling, zone
  firewall, scheduler, connection limits, MAC filtering, PADO delay, and logs.
- X-API-Key authentication with 401 responses.
- Pydantic v2 request/response models (140+ schemas).
- Guarded config apply with auto-revert (checkpoint system).
- SSE streaming for traffic monitoring and log tailing.
- Interactive installer with TUI wizard (`install.sh` v2.0).
- Non-interactive install mode (`--yes` flag) and uninstaller (`--uninstall`).
- Systemd service with security hardening.
- Sudoers configuration with least-privilege rules (6 commands only).
- 808 tests with 100% code coverage.
- Pylint 10.00/10 score.
- Black formatted codebase.
- Zero known vulnerabilities (pip-audit clean).

### Infrastructure (post-release)

- GitHub Actions CI (lint + test, Python 3.9--3.13 matrix).
- GitHub Actions Release (PyPI publish + GitHub Release on tag).
- GitHub Actions Docs (MkDocs Material auto-deploy to GitHub Pages).
- Pre-commit hooks (Black, Ruff, Pylint).
- MkDocs Material documentation site.
- PyPI package: [pypi.org/project/dawos-agent](https://pypi.org/project/dawos-agent/)
