# dawos-agent

[![CI](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dawos-agent)](https://pypi.org/project/dawos-agent/)
[![Python](https://img.shields.io/pypi/pyversions/dawos-agent)](https://pypi.org/project/dawos-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://cepat-kilat-teknologi.github.io/dawos-agent/)

Open-source PPP router management agent. Manages PPPoE sessions, firewall, network, traffic shaping, routing, and system services on Linux-based BNG/concentrator nodes via REST API.

Wraps `accel-cmd`, `nft`, `ip`, `tc`, `vtysh`, and other Linux system utilities as 138 authenticated HTTP endpoints.

## Features

- **PPPoE lifecycle** — sessions, rate-limiting, PADO delay, MAC filtering
- **Network management** — interfaces, VLANs, routes, DNS, DHCP, VRRP, LLDP
- **Firewall** — nftables rules, NAT/masquerade, zone firewall, conntrack
- **Dynamic routing** — BGP, OSPF, RIP, BFD status via FRR/vtysh
- **Config management** — checkpoint, diff, rollback, guarded apply with auto-revert
- **Streaming** — SSE endpoints for live traffic and log tailing
- **Event hooks** — webhooks on session/config events with history
- **Scheduler** — cron-like job scheduling with run-on-demand
- **Hardened** — systemd sandboxing, least-privilege sudoers, API-key auth

## Hardware Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| **CPU** | 1 vCPU | 2+ vCPU | accel-ppp itself needs CPU for PPP |
| **RAM** | 512 MB | 1 GB+ | Agent ~60 MB + accel-ppp ~5 MB + OS |
| **Disk** | 2 GB free | 5 GB+ | 55 MB venv + ~500 MB build deps (if compiling accel-ppp) |
| **OS** | Debian 11 / Ubuntu 22.04 | Ubuntu 24.04 LTS | x86_64 architecture required |
| **Python** | 3.9 | 3.10+ | `python3-venv` module required |
| **Network** | 1 NIC | 2+ NICs | Management + subscriber-facing |

> **Note:** These are requirements for the agent only. accel-ppp BNG workloads (thousands of PPPoE sessions) may need significantly more CPU and RAM — consult the [accel-ppp documentation](https://accel-ppp.readthedocs.io/) for BNG sizing.

## Quick Start

### Install from PyPI

```bash
pip install dawos-agent
```

### Install from source (production)

```bash
curl -sL https://raw.githubusercontent.com/Cepat-Kilat-Teknologi/dawos-agent/main/install.sh | sudo bash
```

Or manually:

```bash
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
sudo bash install.sh
```

The installer automatically builds accel-ppp from source if not already installed.

After install, verify:

```bash
curl -s http://localhost:8470/health | python3 -m json.tool
```

## Configuration

All settings use `DAWOS_` env prefix. Place in `/etc/dawos-agent/agent.env`.

| Variable | Default | Description |
|---|---|---|
| `DAWOS_HOST` | `0.0.0.0` | Listen address |
| `DAWOS_PORT` | `8470` | Listen port |
| `DAWOS_API_KEY` | *(generated)* | Shared secret for `X-API-Key` header |
| `DAWOS_NODE_NAME` | *(hostname)* | Node identity for health responses |
| `DAWOS_ACCEL_CMD` | `/usr/bin/accel-cmd` | Path to accel-cmd |
| `DAWOS_ACCEL_CLI_PORT` | `2001` | accel-ppp CLI port |
| `DAWOS_ACCEL_CONFIG_PATH` | `/etc/accel-ppp.conf` | accel-ppp config path |
| `DAWOS_ACCEL_SERVICE_NAME` | `accel-ppp` | Systemd service name |
| `DAWOS_LOG_LEVEL` | `info` | Log level (`debug`, `info`, `warning`, `error`) |

See [Configuration](https://cepat-kilat-teknologi.github.io/dawos-agent/getting-started/configuration/) for the full reference.

## API

138 endpoints across 29 groups. All require `X-API-Key` header except `/health`.

Interactive docs at `/docs` (Swagger) and `/redoc`.

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

## Authentication

```bash
# with key
curl -H "X-API-Key: your-key" http://bng-node:8470/api/v1/system/info

# without key → 401
curl http://bng-node:8470/api/v1/system/info
```

`/health` is public for load balancer probes.

## Deployment

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 vCPU | 2+ vCPU |
| RAM | 512 MB | 1 GB+ |
| Disk | 2 GB free | 5 GB+ |
| OS | Debian 11+ / Ubuntu 22.04+ | Ubuntu 24.04 LTS |
| Python | 3.9+ | 3.10+ |

```bash
sudo bash install.sh            # interactive
sudo bash install.sh --yes      # non-interactive
sudo bash install.sh --uninstall
```

The installer builds accel-ppp from source if not present, creates a `dawos` system user, sets up a venv at `/opt/dawos-agent/venv`, installs the systemd unit, and configures least-privilege sudoers.

| Path | Purpose |
|---|---|
| `/opt/dawos-agent/` | Install directory |
| `/etc/dawos-agent/agent.env` | Configuration |
| `/etc/accel-ppp.conf` | accel-ppp configuration |
| `/etc/sudoers.d/dawos-agent` | Sudo rules |
| `/etc/systemd/system/dawos-agent.service` | dawos-agent systemd unit |
| `/etc/systemd/system/accel-ppp.service` | accel-ppp systemd unit |

See [Installation](https://cepat-kilat-teknologi.github.io/dawos-agent/getting-started/installation/) for details.

## Documentation

Full documentation available at [cepat-kilat-teknologi.github.io/dawos-agent](https://cepat-kilat-teknologi.github.io/dawos-agent/).

## Development

```bash
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run
DAWOS_API_KEY=dev-key python -m dawos_agent

# test
pytest

# lint & format
pylint dawos_agent/
black --check .
```

## Project Structure

```
dawos_agent/
├── app.py              # FastAPI app, mounts routers
├── auth.py             # X-API-Key auth (401 on invalid)
├── config.py           # pydantic-settings, DAWOS_ prefix
├── models/schemas.py   # Pydantic v2 request/response models
├── routers/            # 30 router modules (HTTP layer)
└── services/           # 28 service modules (business logic + shell)
```

## Security

- API-key auth on all endpoints (except `/health`)
- Systemd sandboxing (`ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`)
- Sudo limited to 6 commands: `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`

See [SECURITY.md](SECURITY.md) for the full security model.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

---

[Cepat Kilat Teknologi](https://github.com/Cepat-Kilat-Teknologi)
