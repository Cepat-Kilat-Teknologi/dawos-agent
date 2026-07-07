# dawos-agent

**REST API daemon for managing PPPoE/BNG routers powered by accel-ppp.**

## What is dawos-agent?

`dawos-agent` is a FastAPI-based management daemon for Linux-based PPPoE BNG (Broadband Network Gateway) nodes. It wraps `accel-cmd`, `nft`, `ip`, `tc`, `vtysh`, and other Linux system utilities as 138 authenticated HTTP endpoints.

### Features

- **PPPoE lifecycle** -- sessions, rate-limiting, PADO delay, MAC filtering
- **Network management** -- interfaces, VLANs, routes, DNS, DHCP, VRRP, LLDP
- **Firewall** -- nftables rules, NAT/masquerade, zone firewall, conntrack
- **Dynamic routing** -- BGP, OSPF, RIP, BFD status via FRR/vtysh
- **Config management** -- checkpoint, diff, rollback, guarded apply with auto-revert
- **Streaming** -- SSE endpoints for live traffic and log tailing
- **Event hooks** -- webhooks on session/config events with history
- **Scheduler** -- cron-like job scheduling with run-on-demand
- **Hardened** -- systemd sandboxing, least-privilege sudoers, API-key auth

### Quick Example

```bash
# Install
pip install dawos-agent

# Run with an API key
DAWOS_API_KEY=your-secret dawos-agent

# Health check
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
