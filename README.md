<p align="center">
  <strong>dawos-agent</strong><br>
  <em>REST API daemon for managing PPPoE/BNG routers powered by accel-ppp.</em><br>
  <a href="https://pypi.org/project/dawos-agent/">PyPI</a> |
  <a href="https://cepat-kilat-teknologi.github.io/dawos-agent/">Documentation</a> |
  <a href="https://github.com/Cepat-Kilat-Teknologi/dawos-agent/releases">Releases</a>
</p>

---

[![CI](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dawos-agent)](https://pypi.org/project/dawos-agent/)
[![Python](https://img.shields.io/pypi/pyversions/dawos-agent)](https://pypi.org/project/dawos-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://cepat-kilat-teknologi.github.io/dawos-agent/)

## Overview

**dawos-agent** is a FastAPI-based management daemon for Linux PPPoE BNG (Broadband Network Gateway) nodes powered by [accel-ppp](https://accel-ppp.org/). It wraps `accel-cmd`, `nft`, `ip`, `tc`, `vtysh`, and other Linux system utilities as **138 authenticated HTTP endpoints** across **29 router modules**.

### Key Features

- **PPPoE lifecycle** -- sessions, rate-limiting, PADO delay, MAC filtering
- **Network management** -- interfaces, VLANs, routes, DNS, DHCP, VRRP, LLDP
- **Firewall** -- nftables rules, NAT/masquerade, zone firewall, conntrack
- **Dynamic routing** -- BGP, OSPF, RIP, BFD status via FRR/vtysh
- **Config management** -- checkpoint, diff, rollback, guarded apply with auto-revert
- **Streaming** -- SSE endpoints for live traffic and log tailing
- **Event hooks** -- webhooks on session/config events with history
- **Scheduler** -- cron-like job scheduling with run-on-demand
- **Hardened** -- systemd sandboxing, least-privilege sudoers, API-key auth

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Authentication](#authentication)
- [Usage Examples](#usage-examples)
- [Deployment](#deployment)
- [Architecture](#architecture)
- [Development](#development)
- [Testing](#testing)
- [Contributing](#contributing)
- [Security](#security)
- [Changelog](#changelog)
- [License](#license)

---

## Installation

### Prerequisites

- **Python 3.9** or later
- **Linux** (Debian 11+ / Ubuntu 22.04+), x86_64 architecture
- **accel-ppp** installed and running

### Quick Install (Recommended)

```bash
pip install dawos-agent
```

### Production Install (with installer script)

The installer script sets up accel-ppp, systemd service, sudoers, and the agent:

```bash
# One-line install
curl -sL https://raw.githubusercontent.com/Cepat-Kilat-Teknologi/dawos-agent/main/install.sh | sudo bash

# Or clone and run manually
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
sudo bash install.sh
```

Options:

```bash
sudo bash install.sh            # Interactive TUI wizard
sudo bash install.sh --yes      # Non-interactive (accept defaults)
sudo bash install.sh --uninstall # Remove everything
```

> The installer builds accel-ppp from source if not already installed, creates a `dawos` system user, sets up a venv at `/opt/dawos-agent/venv`, installs the systemd unit, and configures least-privilege sudoers.

### Install from Source (Development)

```bash
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install pylint black
```

### Upgrade

```bash
pip install --upgrade dawos-agent
```

---

## Quick Start

### 1. Start the Agent

```bash
# Development mode
DAWOS_API_KEY=your-secret python -m dawos_agent

# Production (via systemd)
sudo systemctl start dawos-agent
```

### 2. Verify

```bash
# Health check (no auth required)
curl -s http://localhost:8470/health | python3 -m json.tool

# System info (auth required)
curl -H "X-API-Key: your-secret" http://localhost:8470/api/v1/system/info
```

### 3. Interactive API Docs

Open in your browser:

- **Swagger UI**: `http://localhost:8470/docs`
- **ReDoc**: `http://localhost:8470/redoc`

---

## Configuration

All settings use the `DAWOS_` environment variable prefix. Place them in `/etc/dawos-agent/agent.env` for production.

| Variable | Default | Description |
|---|---|---|
| `DAWOS_HOST` | `0.0.0.0` | Listen address |
| `DAWOS_PORT` | `8470` | Listen port |
| `DAWOS_API_KEY` | *(generated)* | Shared secret for `X-API-Key` header |
| `DAWOS_NODE_NAME` | *(hostname)* | Node identity for health responses |
| `DAWOS_LOG_LEVEL` | `info` | Log level (`debug`, `info`, `warning`, `error`) |
| `ACCEL_CMD` | `/usr/bin/accel-cmd` | Path to accel-cmd |
| `ACCEL_CLI_PORT` | `2001` | accel-ppp CLI port |
| `ACCEL_CONFIG_PATH` | `/etc/accel-ppp.conf` | accel-ppp config path |
| `ACCEL_SERVICE_NAME` | `accel-ppp` | Systemd service name |

See [Configuration docs](https://cepat-kilat-teknologi.github.io/dawos-agent/getting-started/configuration/) for the full reference.

---

## API Reference

138 endpoints across 29 groups. All require `X-API-Key` header except `/health`.

| Group | Endpoints | Description |
|---|:---:|---|
| health | 1 | Liveness probe (public) |
| system | 2 | OS info, CPU, memory, disk |
| service | 3 | Start/stop/restart accel-ppp, accel-cmd passthrough |
| sessions | 4 | List, stats, find, terminate |
| session-control | 5 | Lookup by SID/IP, snapshot, restart |
| config | 3 | Read/update accel-ppp.conf |
| checkpoint | 6 | Revisions, diff, rollback, guarded apply |
| network | 12 | Interfaces, VLANs, routes, DNS |
| firewall | 19 | nftables, NAT, sysctl, conntrack, SNMP |
| firewall-groups | 4 | Named groups with member management |
| pppoe | 6 | Listener interfaces, MAC filter |
| pado-delay | 2 | PADO delay for PPPoE |
| traffic | 5 | SSE streams, TC queues, rate limits |
| routing | 9 | BGP, OSPF, RIP, BFD |
| conntrack | 7 | Table size, timeouts, profiles |
| connection-limits | 3 | Global/per-interface limits |
| ip-pool | 4 | Address pool management |
| scheduler | 4 | Job scheduling with run-on-demand |
| dns-forwarding | 4 | DNS forwarder, cache flush |
| ntp | 2 | NTP sync status |
| lldp | 3 | LLDP neighbor discovery |
| dhcp | 5 | DHCP/relay, leases |
| flow-accounting | 4 | NetFlow/sFlow collectors |
| event-handler | 6 | Event hooks, fire, history |
| zone-firewall | 4 | Zone-based firewall |
| vrrp | 4 | VRRP status, failover |
| monitoring | 4 | Prometheus exporters |
| diagnostics | 1 | System health check |
| logs | 2 | Log tail, SSE stream |

Full API reference: [API Documentation](https://cepat-kilat-teknologi.github.io/dawos-agent/api/reference/)

---

## Authentication

All endpoints except `/health` require an `X-API-Key` header:

```bash
# Authenticated request
curl -H "X-API-Key: your-key" http://bng-node:8470/api/v1/system/info

# Without key -> 401 Unauthorized
curl http://bng-node:8470/api/v1/system/info

# Health check (public, no key required)
curl http://bng-node:8470/health
```

Generate a strong API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Usage Examples

### Session Management

```bash
# List active sessions
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/sessions/list

# Session statistics
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/sessions/stats

# Find a user
curl -H "X-API-Key: $KEY" "http://$HOST:8470/api/v1/sessions/find?username=john"

# Terminate a session
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"username":"john"}' http://$HOST:8470/api/v1/sessions/terminate
```

### Service Control

```bash
# Service status
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/service/status

# Restart accel-ppp
curl -X POST -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/service/restart

# Reload config (graceful, no session drop)
curl -X POST -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/service/reload
```

### Configuration with Guarded Apply

```bash
# Show current config
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/config/show

# Apply new config (auto-reverts if not confirmed within timeout)
curl -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"content":"..."}' http://$HOST:8470/api/v1/checkpoint/apply

# Confirm the apply (prevents auto-rollback)
curl -X POST -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/checkpoint/confirm
```

### Network and Firewall

```bash
# List interfaces
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/network/interfaces

# List routes
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/network/routes

# Firewall status
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/firewall/status

# BGP summary
curl -H "X-API-Key: $KEY" http://$HOST:8470/api/v1/routing/bgp
```

### Using with dawos-cli

For a rich terminal experience, use the companion CLI tool [dawos-cli](https://github.com/Cepat-Kilat-Teknologi/dawos-cli):

```bash
pip install dawos-cli
dawos profile add prod --url http://bng-node:8470 --key YOUR_KEY
dawos status
dawos session list
dawos top    # live dashboard
```

---

## Deployment

### Hardware Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| **CPU** | 1 vCPU | 2+ vCPU | accel-ppp itself needs CPU for PPP |
| **RAM** | 512 MB | 1 GB+ | Agent ~60 MB + accel-ppp ~5 MB + OS |
| **Disk** | 2 GB free | 5 GB+ | 55 MB venv + ~500 MB build deps (if compiling accel-ppp) |
| **OS** | Debian 11 / Ubuntu 22.04 | Ubuntu 24.04 LTS | x86_64 architecture required |
| **Python** | 3.9 | 3.10+ | `python3-venv` module required |
| **Network** | 1 NIC | 2+ NICs | Management + subscriber-facing |

> **Note:** These are requirements for the agent only. accel-ppp BNG workloads (thousands of PPPoE sessions) may need significantly more CPU and RAM -- consult the [accel-ppp documentation](https://accel-ppp.readthedocs.io/) for BNG sizing.

### File Locations

| Path | Purpose |
|---|---|
| `/opt/dawos-agent/` | Install directory |
| `/opt/dawos-agent/venv/` | Python virtual environment |
| `/etc/dawos-agent/agent.env` | Configuration (DAWOS_* vars) |
| `/etc/accel-ppp.conf` | accel-ppp configuration |
| `/etc/sudoers.d/dawos-agent` | Sudo rules |
| `/etc/systemd/system/dawos-agent.service` | dawos-agent systemd unit |
| `/etc/systemd/system/accel-ppp.service` | accel-ppp systemd unit |

### Systemd Management

```bash
sudo systemctl start dawos-agent
sudo systemctl stop dawos-agent
sudo systemctl restart dawos-agent
sudo systemctl status dawos-agent
sudo journalctl -u dawos-agent -f
```

See [Installation docs](https://cepat-kilat-teknologi.github.io/dawos-agent/getting-started/installation/) for full deployment details.

---

## Architecture

```
dawos-agent/
├── dawos_agent/
│   ├── __init__.py          # Package metadata
│   ├── __main__.py          # uvicorn entry point
│   ├── app.py               # FastAPI app factory, mounts all routers
│   ├── auth.py              # X-API-Key header auth (returns 401, NOT 403)
│   ├── config.py            # pydantic-settings, DAWOS_ env prefix
│   ├── models/
│   │   └── schemas.py       # 140+ Pydantic v2 request/response models
│   ├── routers/             # 29 API router modules (HTTP layer only)
│   │   ├── checkpoint.py    # Config checkpoint, diff, rollback, guarded apply
│   │   ├── config.py        # Config read/update
│   │   ├── conntrack.py     # Connection tracking
│   │   ├── dhcp.py          # DHCP server and relay
│   │   ├── diagnostics.py   # System health check
│   │   ├── dns.py           # DNS forwarding
│   │   ├── event_handler.py # Event hooks and webhooks
│   │   ├── firewall.py      # nftables, NAT, sysctl, conntrack
│   │   ├── flow.py          # NetFlow/sFlow collectors
│   │   ├── lldp.py          # LLDP discovery
│   │   ├── logs.py          # Log tail, SSE stream
│   │   ├── monitoring.py    # Prometheus exporters
│   │   ├── nat.py           # NAT masquerade
│   │   ├── network.py       # Interfaces, routes, VLANs, DNS
│   │   ├── ntp.py           # NTP time sync
│   │   ├── pool.py          # IP address pools
│   │   ├── pppoe.py         # PPPoE interfaces, MAC filter
│   │   ├── routing.py       # BGP, OSPF, RIP, BFD
│   │   ├── scheduler.py     # Job scheduling
│   │   ├── service.py       # Service start/stop/restart
│   │   ├── sessions.py      # Session list, stats, find, terminate
│   │   ├── traffic.py       # SSE streams, TC queues, rate limits
│   │   ├── vrrp.py          # VRRP high-availability
│   │   └── zone.py          # Zone-based firewall
│   └── services/            # 27 service modules (business logic + shell calls)
├── tests/                   # 808 tests, 100% coverage
├── docs/                    # MkDocs Material documentation
├── .github/
│   └── workflows/
│       ├── ci.yml           # GitHub Actions CI (lint + test on push/PR)
│       ├── release.yml      # PyPI publish + GitHub Release on tag
│       └── docs.yml         # MkDocs auto-deploy to GitHub Pages
├── .pre-commit-config.yaml  # Pre-commit hooks (Black, Ruff, Pylint)
├── mkdocs.yml               # MkDocs configuration
├── install.sh               # Production installer script (TUI wizard)
├── pyproject.toml           # Project metadata, build config, tool settings
├── README.md                # This file
├── CHANGELOG.md             # Version history
├── CONTRIBUTING.md          # Contribution guidelines
├── SECURITY.md              # Security policy
├── CODE_OF_CONDUCT.md       # Community guidelines
└── LICENSE                  # MIT License
```

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Router -> Service -> Shell** | Routers handle HTTP, services contain business logic, shell commands via `_run()`. |
| **Auth on every endpoint** | `ApiKey` dependency returns 401 on missing/invalid key. `/health` is the only public endpoint. |
| **Pydantic v2 models** | All request/response types defined in `models/schemas.py` with strict validation. |
| **Least-privilege sudo** | Only 6 commands allowed: `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`. |
| **No shell injection** | All subprocess calls use list-form arguments, never string interpolation. |
| **Systemd sandboxing** | `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=yes`. |

---

## Development

### Environment Setup

```bash
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install pylint black
```

### Code Quality Tools

| Tool | Purpose | Configuration |
|------|---------|---------------|
| **[Black](https://black.readthedocs.io/)** | Code formatting | `pyproject.toml` `[tool.black]` |
| **[Pylint](https://pylint.readthedocs.io/)** | Static analysis (10.00/10 required) | `pyproject.toml` `[tool.pylint]` |
| **[Ruff](https://docs.astral.sh/ruff/)** | Fast linting (E/F/W/I/N/UP/B/SIM) | `pyproject.toml` `[tool.ruff]` |
| **[pytest](https://docs.pytest.org/)** | Test framework with async support | `pyproject.toml` `[tool.pytest]` |
| **[coverage](https://coverage.readthedocs.io/)** | Coverage reporting (100% required) | `pyproject.toml` `[tool.coverage]` |
| **[pre-commit](https://pre-commit.com/)** | Git hooks (Black + Ruff + Pylint) | `.pre-commit-config.yaml` |

### Running Quality Checks

```bash
# Format code
black dawos_agent/ tests/

# Lint
pylint dawos_agent/
ruff check dawos_agent/ tests/

# Run all tests
pytest tests/ -x -q

# Run with coverage
coverage run -m pytest tests/
coverage report -m

# All checks at once
black --check dawos_agent/ tests/ && ruff check dawos_agent/ tests/ && pylint dawos_agent/ && pytest tests/ -x -q
```

### Pre-commit Hooks

Pre-commit hooks run Black, Ruff, and Pylint automatically on `git commit`:

```bash
# Install hooks (one-time setup)
pip install pre-commit
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Running Locally

```bash
DAWOS_API_KEY=dev-key python -m dawos_agent
```

The agent starts on `http://localhost:8470` with Swagger docs at `/docs`.

---

## Testing

The project maintains **808 tests** with **100% coverage** across all source files:

```bash
# Quick test run
pytest tests/ -x -q

# Full coverage report
coverage run -m pytest tests/ && coverage report -m
```

### Quality Gates

| Gate | Target | Command |
|------|--------|---------|
| Tests | 808 passing | `pytest tests/ -x -q` |
| Coverage | 100% | `coverage report -m` |
| Pylint | 10.00/10 | `pylint dawos_agent/` |
| Black | All formatted | `black --check dawos_agent/ tests/` |
| Ruff | Zero violations | `ruff check dawos_agent/ tests/` |
| Vulnerabilities | 0 known | `pip-audit` |

### Test Patterns

- **Mirror source structure** -- each service gets `test_xxx_service.py`, each router gets `test_xxx.py`
- **Mock at shell level** -- mock `asyncio.create_subprocess_exec` or service functions
- **Async tests** -- use `pytest-asyncio` with `asyncio_mode="auto"`
- **Edge cases** -- error paths, empty data, subprocess failures

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:

- Setting up your development environment
- Code style and formatting standards (Black, Pylint 10.0/10, Ruff)
- Testing requirements (808+ tests, 100% coverage)
- Submitting pull requests

---

## Security

- **API-key auth** on all endpoints (except `/health`)
- **Systemd sandboxing** (`ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`)
- **Least-privilege sudo** limited to 6 commands: `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`
- **No shell injection** -- all subprocess calls use list-form arguments
- **No `eval()` or `exec()`** anywhere in the codebase

See [SECURITY.md](SECURITY.md) for the full security policy.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed version history.

---

## API Compatibility

dawos-agent exposes a REST API on port 8470 consumed by [dawos-cli](https://github.com/Cepat-Kilat-Teknologi/dawos-cli). All endpoints use `X-API-Key` header authentication.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.

---

<p align="center">
  <sub>Built with <a href="https://fastapi.tiangolo.com/">FastAPI</a>, <a href="https://docs.pydantic.dev/">Pydantic v2</a>, and <a href="https://www.uvicorn.org/">Uvicorn</a>.</sub>
</p>
