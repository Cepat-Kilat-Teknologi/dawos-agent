# DawOS Agent

**Broadband management, simplified.**

[![CI](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dawos-agent)](https://pypi.org/project/dawos-agent/)
[![Python](https://img.shields.io/pypi/pyversions/dawos-agent)](https://pypi.org/project/dawos-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/LICENSE)

## What is DawOS Agent?

DawOS Agent is an open-source broadband network gateway management daemon built on FastAPI. It wraps `accel-cmd`, `nft`, `ip`, `tc`, `vtysh`, and other Linux system utilities as **151 HTTP endpoints** across **34 router modules**, giving you full control of your [accel-ppp](https://accel-ppp.org/) PPPoE infrastructure through a single REST API.

The agent runs as a lightweight single-process daemon (64 MB RSS at idle) alongside accel-ppp on the same node. It provides complete remote management without direct SSH access.

### Features

- **PPPoE lifecycle** -- sessions, rate-limiting, PADO delay, MAC filtering
- **Network management** -- interfaces, VLANs, routes, DNS, DHCP, VRRP, LLDP
- **Firewall** -- nftables rules, NAT/masquerade, zone firewall, conntrack
- **Dynamic routing** -- BGP, OSPF, RIP, BFD status via FRR/vtysh
- **Config management** -- checkpoint, diff, rollback, guarded apply with auto-revert
- **Monitoring** -- Prometheus metrics endpoint, health/readiness probes, WebSocket event streaming
- **Security** -- API-key auth with RBAC (viewer/operator/admin), rate limiting, systemd sandboxing
- **Observability** -- structured JSON logging, request ID tracing, audit log, webhook notifications
- **Automation** -- operational playbooks, bulk operations, cron-like scheduler
- **Streaming** -- SSE endpoints for live traffic and log tailing

### Quick Example

```bash
# Install from PyPI
pip install dawos-agent

# Run with an API key
DAWOS_API_KEY=your-secret dawos-agent

# Health check (public)
curl http://localhost:8470/health

# List sessions (requires API key)
curl -H "X-API-Key: your-secret" http://localhost:8470/api/v1/sessions/list
```

## Requirements

- Python 3.9+
- Linux (Debian 11+ / Ubuntu 22.04+)
- accel-ppp installed and running

## Install

```bash
pip install dawos-agent
```

See [Installation](getting-started/installation.md) for production deployment with the installer script.

## Companion CLI

For a rich terminal experience, use [dawos-cli](https://github.com/Cepat-Kilat-Teknologi/dawos-cli):

```bash
pip install dawos-cli
dawos profile add prod --url http://bng-node:8470 --key YOUR_KEY
dawos status
dawos session list
dawos top    # live dashboard
```

## Quality

| Metric | Value |
|--------|-------|
| Tests | 1133 passing |
| Coverage | minimum 90% |
| Pylint | 10.00/10 |
| Black | Formatted |
| Ruff | Zero violations |
| Vulnerabilities | 0 known (pip-audit) |

## Links

- [PyPI](https://pypi.org/project/dawos-agent/)
- [GitHub](https://github.com/Cepat-Kilat-Teknologi/dawos-agent)
- [Changelog](development/changelog.md)
- [Contributing](development/contributing.md)
- [Security Policy](development/security.md)
