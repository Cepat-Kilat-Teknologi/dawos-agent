<p align="center">
  <strong>DawOS Agent</strong><br>
  <em>Broadband management, simplified.</em><br>
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

**DawOS Agent** is an open-source broadband network gateway management daemon built on FastAPI. It wraps `accel-cmd`, `nft`, `ip`, `tc`, `vtysh`, and other Linux system utilities as **149 authenticated HTTP endpoints** across **34 router modules**, giving you full control of your [accel-ppp](https://accel-ppp.org/) PPPoE infrastructure through a single REST API.

The agent runs as a lightweight single-process daemon (64 MB RSS at idle) alongside accel-ppp on the same node. It provides complete remote management without direct SSH access, making it suitable for automation, orchestration platforms, and multi-node ISP deployments.

### Key Features

- **PPPoE lifecycle** -- sessions, rate-limiting, PADO delay, MAC filtering
- **Network management** -- interfaces, VLANs, routes, DNS, DHCP, VRRP, LLDP
- **Firewall** -- nftables rules, NAT/masquerade, zone firewall, conntrack
- **Dynamic routing** -- BGP, OSPF, RIP, BFD status via FRR/vtysh
- **Config management** -- checkpoint, diff, rollback, guarded apply with auto-revert
- **Monitoring** -- Prometheus metrics endpoint, health/readiness probes, WebSocket event streaming
- **Security** -- API-key auth with RBAC (viewer/operator/admin), rate limiting, systemd sandboxing, least-privilege sudoers
- **Observability** -- structured JSON logging, request ID tracing, audit log with in-memory buffer, webhook notifications
- **Automation** -- operational playbooks, bulk operations, cron-like scheduler
- **Streaming** -- SSE endpoints for live traffic and log tailing

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

The installer builds accel-ppp from source if not already installed, creates a `dawos` system user, sets up a venv at `/opt/dawos-agent/venv`, installs the systemd unit, configures least-privilege sudoers, and sets correct file ownership for accel-ppp config management.

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

# Readiness probe (checks accel-ppp connectivity)
curl -s http://localhost:8470/health/ready | python3 -m json.tool

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
| `DAWOS_LOG_FORMAT` | `text` | Log format (`text` or `json` for structured logging) |
| `DAWOS_RATE_LIMIT` | `120/minute` | Per-IP rate limit (empty to disable) |
| `DAWOS_RETRY_MAX` | `3` | Max retry attempts for transient accel-cmd failures |
| `DAWOS_RETRY_DELAY` | `1.0` | Base retry delay in seconds |
| `DAWOS_AUDIT_BUFFER_SIZE` | `1000` | In-memory audit ring buffer size |
| `DAWOS_WEBHOOK_URL` | *(disabled)* | Webhook endpoint for event notifications |
| `DAWOS_WEBHOOK_SECRET` | *(disabled)* | HMAC-SHA256 secret for webhook signing |
| `DAWOS_API_KEYS_FILE` | *(disabled)* | JSON file mapping API keys to RBAC roles |
| `ACCEL_CMD` | `/usr/bin/accel-cmd` | Path to accel-cmd |
| `ACCEL_CLI_PORT` | `2001` | accel-ppp CLI port |
| `ACCEL_CONFIG_PATH` | `/etc/accel-ppp.conf` | accel-ppp config path |
| `ACCEL_SERVICE_NAME` | `accel-ppp` | Systemd service name |

See [Configuration docs](https://cepat-kilat-teknologi.github.io/dawos-agent/getting-started/configuration/) for the full reference.

---

## API Reference

149 endpoints across 34 groups. All require `X-API-Key` header except `/health`, `/health/ready`, and `/metrics`.

| Group | Endpoints | Description |
|---|:---:|---|
| health | 2 | Liveness and readiness probes (public) |
| metrics | 1 | Prometheus metrics (public) |
| system | 2 | OS info, CPU, memory, disk |
| service | 3 | Start/stop/restart accel-ppp, accel-cmd passthrough |
| sessions | 4 | List, stats, find, terminate |
| session-control | 5 | Lookup by SID/IP, snapshot, restart |
| config | 3 | Read/update accel-ppp.conf |
| checkpoint | 8 | Revisions, diff, rollback, guarded apply, confirm |
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
| audit | 1 | Write operation trail (admin-only) |
| bulk | 3 | Batch API operations |
| playbooks | 2 | Operational automation sequences |
| websocket | 1 | Real-time event streaming |

Full API reference: [API Documentation](https://cepat-kilat-teknologi.github.io/dawos-agent/api/reference/)

---

## Authentication

All endpoints except `/health`, `/health/ready`, and `/metrics` require an `X-API-Key` header:

```bash
# Authenticated request
curl -H "X-API-Key: your-key" http://bng-node:8470/api/v1/system/info

# Without key -> 401 Unauthorized
curl http://bng-node:8470/api/v1/system/info

# Health check (public, no key required)
curl http://bng-node:8470/health
```

### RBAC Roles

| Role | Access | Use Case |
|------|--------|----------|
| viewer | GET endpoints only | Monitoring dashboards, read-only scripts |
| operator | GET + POST/PUT/DELETE | Day-to-day management |
| admin | Full access | Service restart, config apply, audit log, playbooks |

The primary `DAWOS_API_KEY` always grants admin access. For multi-key RBAC, configure `DAWOS_API_KEYS_FILE` with a JSON mapping.

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

### Monitoring

```bash
# Prometheus metrics
curl http://$HOST:8470/metrics

# Readiness probe
curl http://$HOST:8470/health/ready

# WebSocket event stream (requires wscat or websocat)
wscat -c "ws://$HOST:8470/ws/events?key=$KEY"
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

### Measured Resource Usage

| Component | Memory (RSS) | CPU (idle) | CPU (under load) |
|-----------|:------------:|:----------:|:-----------------:|
| dawos-agent (FastAPI + Uvicorn) | 64 MB | < 0.1% | < 2% |
| accel-ppp daemon (0 sessions) | 6 MB | 0% | varies |
| Combined management stack | **70 MB** | **< 0.2%** | **< 3%** |

### Sizing by Scale

| Scale | Sessions | CPU | RAM | Disk |
|-------|:--------:|:---:|:---:|:----:|
| Small | < 500 | 2 vCPU | 2 GB | 10 GB |
| Medium | 500 -- 2,000 | 2 vCPU | 4 GB | 20 GB |
| Large | 2,000 -- 10,000 | 4 vCPU | 8 GB | 40 GB |

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

See [Installation docs](https://cepat-kilat-teknologi.github.io/dawos-agent/getting-started/installation/) for full deployment details and the [Production Hardening guide](https://cepat-kilat-teknologi.github.io/dawos-agent/guides/production-hardening/) for production-ready configuration.

---

## Architecture

```
dawos-agent/
├── dawos_agent/
│   ├── __init__.py          # Package metadata
│   ├── __main__.py          # uvicorn entry point
│   ├── app.py               # FastAPI app factory, mounts all routers
│   ├── auth.py              # X-API-Key header auth with RBAC
│   ├── config.py            # pydantic-settings, DAWOS_ env prefix
│   ├── constants.py         # Shared named constants
│   ├── events.py            # WebSocket event bus (4 channels)
│   ├── logging.py           # Structured logging setup (text/JSON)
│   ├── metrics.py           # Prometheus metric definitions
│   ├── middleware.py         # RequestId + AuditLog + Metrics middleware
│   ├── rbac.py              # Role-based access control (viewer/operator/admin)
│   ├── retry.py             # Exponential backoff retry for accel-cmd
│   ├── webhooks.py          # Fire-and-forget webhook delivery
│   ├── models/
│   │   └── schemas.py       # 188 Pydantic v2 request/response models
│   ├── routers/             # 34 API router modules (HTTP layer only)
│   └── services/            # 29 service modules (business logic + shell calls)
├── tests/                   # 1133 tests
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
| **Auth on every endpoint** | `ApiKey` dependency returns 401 on missing/invalid key. `/health`, `/health/ready`, `/metrics` are the only public endpoints. |
| **Pydantic v2 models** | All request/response types defined in `models/schemas.py` with strict validation. |
| **Least-privilege sudo** | Only 6 commands allowed: `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`. |
| **No shell injection** | All subprocess calls use list-form arguments, never string interpolation. Defense-in-depth `shlex.quote()` on user-supplied values. |
| **Systemd sandboxing** | `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `WatchdogSec=30`. |

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
| **[Pylint](https://pylint.readthedocs.io/)** | Static analysis | `pyproject.toml` `[tool.pylint]` |
| **[Ruff](https://docs.astral.sh/ruff/)** | Fast linting (E/F/W/I/N/UP/B/SIM) | `pyproject.toml` `[tool.ruff]` |
| **[pytest](https://docs.pytest.org/)** | Test framework with async support | `pyproject.toml` `[tool.pytest]` |
| **[coverage](https://coverage.readthedocs.io/)** | Coverage reporting | `pyproject.toml` `[tool.coverage]` |
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

```bash
# Quick test run
pytest tests/ -x -q

# Full coverage report
coverage run -m pytest tests/ && coverage report -m
```

### Quality Gates

| Gate | Target | Command |
|------|--------|---------|
| Tests | 1133 passing | `pytest tests/ -x -q` |
| Coverage | minimum 90% | `coverage report -m` |
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

We welcome contributions. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:

- Setting up your development environment
- Code style and formatting standards (Black, Pylint 10.0/10, Ruff)
- Testing requirements
- Submitting pull requests

---

## Security

- **API-key auth with RBAC** -- three-tier role hierarchy (viewer, operator, admin) on all endpoints except public probes
- **Rate limiting** -- per-IP throttling with configurable limits, HTTP 429 responses
- **Systemd sandboxing** -- `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `WatchdogSec=30`
- **Least-privilege sudo** -- limited to 6 commands: `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`
- **No shell injection** -- all subprocess calls use list-form arguments with `shlex.quote()` defense-in-depth
- **No `eval()` or `exec()`** anywhere in the codebase
- **Webhook signing** -- optional HMAC-SHA256 payload verification

See [SECURITY.md](SECURITY.md) for the full security policy and vulnerability reporting process.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed version history.

---

## API Compatibility

DawOS Agent exposes a REST API on port 8470 consumed by [DawOS CLI](https://github.com/Cepat-Kilat-Teknologi/dawos-cli). All endpoints use `X-API-Key` header authentication. The WebSocket endpoint at `/ws/events` accepts the key as a query parameter.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.

---

<p align="center">
  <sub>DawOS Agent is built with <a href="https://fastapi.tiangolo.com/">FastAPI</a>, <a href="https://docs.pydantic.dev/">Pydantic v2</a>, and <a href="https://www.uvicorn.org/">Uvicorn</a>.</sub>
</p>
