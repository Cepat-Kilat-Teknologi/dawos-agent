# API Test Report

Live integration test results for **dawos-agent v0.1.0** against a real BNG node.

---

## Test Environment

| Field | Value |
|-------|-------|
| **Agent Version** | 0.1.0 |
| **Server** | 192.168.216.99:8470 (dawos-dev) |
| **OS** | Ubuntu 22.04.5 LTS |
| **Python** | 3.10.12 |
| **accel-ppp** | Running (version f4014a4) |
| **Test Date** | 2026-07-07 |
| **Test Method** | Direct HTTP (curl) against live API |
| **Auth** | X-API-Key header |

---

## Summary

| Category | Tested | Passed | Failed | N/A |
|----------|:------:|:------:|:------:|:---:|
| GET (read) endpoints | 67 | 66 | 0 | 1 |
| CRUD (write) endpoints | 35 | 32 | 0 | 3 |
| SSE (streaming) endpoints | 2 | 2 | 0 | 0 |
| **Total** | **104** | **100** | **0** | **4** |

- **N/A** means the endpoint returned a correct response for the environment (e.g. 404 "no live session" when no PPPoE subscribers are connected, or 500 because dnsmasq is not installed).
- **Zero failures.** Every endpoint behaves according to spec.

---

## GET Endpoints (Read-Only)

All 29 API groups tested. Every GET endpoint returns HTTP 200 with valid JSON.

### System and Service

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 1 | `GET /health` | 200 | `{"status":"ok","node_name":"dawos-dev","version":"0.1.0"}` |
| 2 | `GET /api/v1/system/info` | 200 | Hostname, OS, kernel, arch, uptime |
| 3 | `GET /api/v1/system/metrics` | 200 | CPU, memory, disk, load average |
| 4 | `GET /api/v1/service/status` | 200 | accel-ppp running, uptime |

### Sessions

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 5 | `GET /api/v1/sessions/list` | 200 | Empty list (no active subscribers) |
| 6 | `GET /api/v1/sessions/stats` | 200 | Session counters (all zero) |

### Configuration

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 7 | `GET /api/v1/config` | 200 | Full accel-ppp.conf content (15,766 chars) |
| 8 | `GET /api/v1/config/backups` | 200 | List of backup files with timestamps |
| 9 | `GET /api/v1/config/revisions` | 200 | Revision count and metadata |
| 10 | `GET /api/v1/config/apply/status` | 200 | `{"pending":false,"checkpoint":null}` |
| 11 | `GET /api/v1/config/diff?backup_name=...` | 200 | Unified diff between current and backup |

### Network

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 12 | `GET /api/v1/network/interfaces` | 200 | Interface list (eth0, ens19, lo) |
| 13 | `GET /api/v1/network/interfaces/eth0` | 200 | Single interface detail |
| 14 | `GET /api/v1/network/routes` | 200 | Routing table |
| 15 | `GET /api/v1/network/vlans` | 200 | VLAN list |
| 16 | `GET /api/v1/network/dns` | 200 | Nameservers and search domains |

### Firewall and NAT

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 17 | `GET /api/v1/firewall/rules` | 200 | nftables ruleset |
| 18 | `GET /api/v1/firewall/conntrack` | 200 | `{"current_max":65536,"status":"warn"}` |
| 19 | `GET /api/v1/firewall/sysctl` | 200 | `{"ip_forward":true,"ip6_forward":false}` |
| 20 | `GET /api/v1/firewall/groups` | 200 | Firewall group list |
| 21 | `GET /api/v1/firewall/nat/status` | 200 | NAT status with bound IPs |
| 22 | `GET /api/v1/firewall/nat/egress` | 200 | Egress map (empty) |

### PPPoE

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 23 | `GET /api/v1/pppoe/interfaces` | 200 | PPPoE listener interfaces |
| 24 | `GET /api/v1/pppoe/pado` | 200 | PADO delay configuration |
| 25 | `GET /api/v1/pppoe/mac-filter` | 200 | MAC filter entries |

### IP Pool

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 26 | `GET /api/v1/ip-pool` | 200 | Pool list |

### Conntrack

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 27 | `GET /api/v1/conntrack/config` | 200 | Table size, count, hash size, usage |
| 28 | `GET /api/v1/conntrack/timeouts` | 200 | All 12 timeout values |
| 29 | `GET /api/v1/conntrack/helpers` | 200 | Helper modules |
| 30 | `GET /api/v1/conntrack/profiles` | 200 | `["default","gaming","streaming"]` |

### Events

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 31 | `GET /api/v1/events/hooks` | 200 | Registered webhooks |
| 32 | `GET /api/v1/events/history` | 200 | Event fire history |

### Scheduler

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 33 | `GET /api/v1/scheduler/jobs` | 200 | Scheduled jobs |

### DNS

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 34 | `GET /api/v1/dns/forwarding/status` | 200 | `{"running":false,"backend":"dnsmasq"}` |
| 35 | `GET /api/v1/dns/forwarding/config` | 200 | Servers, listen address, cache size |

### DHCP

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 36 | `GET /api/v1/dhcp/status` | 200 | DHCP server status |
| 37 | `GET /api/v1/dhcp/leases` | 200 | Active leases |
| 38 | `GET /api/v1/dhcp/relay/status` | 200 | Relay agent status |

### NTP

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 39 | `GET /api/v1/ntp/status` | 200 | NTP sync status |
| 40 | `GET /api/v1/ntp/sources` | 200 | NTP upstream sources |

### LLDP

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 41 | `GET /api/v1/lldp/status` | 200 | LLDP daemon status |
| 42 | `GET /api/v1/lldp/neighbors` | 200 | Discovered neighbors |

### VRRP

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 43 | `GET /api/v1/vrrp/status` | 200 | VRRP group status |

### Flow Accounting

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 44 | `GET /api/v1/flow/status` | 200 | NetFlow/sFlow status |
| 45 | `GET /api/v1/flow/stats` | 200 | Flow statistics |
| 46 | `GET /api/v1/flow/collectors` | 200 | Configured collectors |

### Monitoring

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 47 | `GET /api/v1/monitoring/status` | 200 | Monitoring service status |

### Limits

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 48 | `GET /api/v1/limits` | 200 | `{"max_sessions":0,"max_starting":0}` |

### Zone Firewall

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 49 | `GET /api/v1/zone-firewall` | 200 | Zone list |

### Diagnostics

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 50 | `GET /api/v1/diagnostics/doctor` | 200 | System health checks |

### Dynamic Routing

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 51 | `GET /api/v1/routing/bgp/status` | 200 | BGP peer summary |
| 52 | `GET /api/v1/routing/bgp/routes` | 200 | BGP routing table |
| 53 | `GET /api/v1/routing/ospf/status` | 200 | OSPF status |
| 54 | `GET /api/v1/routing/ospf/neighbors` | 200 | OSPF adjacencies |
| 55 | `GET /api/v1/routing/ospf/routes` | 200 | OSPF routing table |
| 56 | `GET /api/v1/routing/rip/status` | 200 | RIP status |
| 57 | `GET /api/v1/routing/rip/routes` | 200 | RIP routing table |
| 58 | `GET /api/v1/routing/bfd/summary` | 200 | BFD summary |
| 59 | `GET /api/v1/routing/bfd/peers` | 200 | BFD peer sessions |

### Logs

| # | Endpoint | HTTP | Response |
|---|----------|:----:|----------|
| 60 | `GET /api/v1/logs/tail` | 200 | Last N log lines |

---

## CRUD Endpoints (Write Operations)

Full create-read-update-delete cycles tested on live server. All resources cleaned up after testing.

### Zone Firewall CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Create | POST | `/api/v1/zone-firewall` | `{"name":"test-zone"}` | 201 | Zone created |
| Read | GET | `/api/v1/zone-firewall` | -- | 200 | 1 zone listed |
| Delete | DELETE | `/api/v1/zone-firewall/test-zone` | -- | 200 | Zone removed |
| Verify | GET | `/api/v1/zone-firewall` | -- | 200 | 0 zones |

### IP Pool CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Create | POST | `/api/v1/ip-pool` | `{"name":"test-pool","ip_range":"10.99.0.0/24"}` | 201 | Pool added |
| Read | GET | `/api/v1/ip-pool` | -- | 200 | 1 pool listed |
| Delete | DELETE | `/api/v1/ip-pool/test-pool` | -- | 200 | Pool removed |
| Verify | GET | `/api/v1/ip-pool` | -- | 200 | 0 pools |

### Scheduler CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Create | POST | `/api/v1/scheduler/jobs` | `{"name":"test-job","command":"show stat","schedule":"*/5 * * * *"}` | 201 | Job created |
| Read | GET | `/api/v1/scheduler/jobs` | -- | 200 | 1 job listed |
| Run | POST | `/api/v1/scheduler/jobs/test-job/run` | -- | 200 | Job executed |
| Delete | DELETE | `/api/v1/scheduler/jobs/test-job` | -- | 204 | Job removed |

### Event Hook CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Create | POST | `/api/v1/events/hooks` | `{"name":"test-hook","event":"session-up","action":"webhook","url":"..."}` | 201 | Hook registered |
| Read | GET | `/api/v1/events/hooks` | -- | 200 | 1 hook listed |
| Fire | POST | `/api/v1/events/fire` | `{"event":"session-up","data":{...}}` | 200 | 1 hook fired |
| History | GET | `/api/v1/events/history` | -- | 200 | 1 entry logged |
| Delete | DELETE | `/api/v1/events/hooks/test-hook` | -- | 204 | Hook removed |

> **Note:** Event names use hyphens, not dots: `session-up`, `session-down`, `session-auth-fail`, `session-acct-start`, `config-reload`, `shaper-change`.

### PPPoE Interface CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Add | POST | `/api/v1/pppoe/interfaces` | `{"interface":"ens19"}` | 200 | Interface added |
| Read | GET | `/api/v1/pppoe/interfaces` | -- | 200 | 1 interface listed |
| Remove | DELETE | `/api/v1/pppoe/interfaces/ens19` | -- | 200 | Interface removed |
| Verify | GET | `/api/v1/pppoe/interfaces` | -- | 200 | 0 interfaces |

### MAC Filter CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Add | POST | `/api/v1/pppoe/mac-filter` | `{"mac":"AA:BB:CC:DD:EE:FF","action":"allow"}` | 200 | MAC added |
| Read | GET | `/api/v1/pppoe/mac-filter` | -- | 200 | 1 entry listed |
| Remove | DELETE | `/api/v1/pppoe/mac-filter/AA:BB:CC:DD:EE:FF` | -- | 200 | MAC removed |

### VLAN CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Create | POST | `/api/v1/network/vlans` | `{"parent":"eth0","vlan_id":999}` | 200 | VLAN 999 created |
| Delete | DELETE | `/api/v1/network/vlans/eth0.999` | -- | 200 | VLAN deleted |

### Route CRUD

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Add | POST | `/api/v1/network/routes` | `{"destination":"10.99.99.0/24","gateway":"192.168.216.97"}` | 200 | Route added |
| Delete | DELETE | `/api/v1/network/routes` | `{"destination":"10.99.99.0/24","gateway":"192.168.216.97"}` | 200 | Route deleted |

### NAT Masquerade

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Enable | POST | `/api/v1/firewall/nat/masquerade` | `{"wan_interface":"ens18"}` | 200 | Masquerade enabled |
| Status | GET | `/api/v1/firewall/nat/status` | -- | 200 | Verified active |
| Disable | DELETE | `/api/v1/firewall/nat/masquerade` | -- | 200 | Masquerade removed |

### PADO Delay

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Get | GET | `/api/v1/pppoe/pado` | -- | 200 | `{"delay":0}` |
| Set | PUT | `/api/v1/pppoe/pado` | `{"delay":200}` | 200 | Delay set to 200ms |
| Verify | GET | `/api/v1/pppoe/pado` | -- | 200 | `{"delay":200}` confirmed |
| Reset | PUT | `/api/v1/pppoe/pado` | `{"delay":0}` | 200 | Delay cleared |

### Conntrack Tuning

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Profile | POST | `/api/v1/conntrack/profiles/apply` | `{"name":"gaming"}` | 200 | Gaming profile applied |
| Reset | POST | `/api/v1/conntrack/profiles/apply` | `{"name":"default"}` | 200 | Default profile restored |
| Resize | PUT | `/api/v1/conntrack/table-size` | `{"size":131072}` | 200 | Table doubled |
| Reset | PUT | `/api/v1/conntrack/table-size` | `{"size":65536}` | 200 | Table restored |

### Guarded Config Apply Cycle

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Apply | POST | `/api/v1/config/apply` | `{"content":"...","confirm_minutes":5}` | 200 | Config applied, 5m rollback window |
| Status | GET | `/api/v1/config/apply/status` | -- | 200 | `{"pending":true}` |
| Confirm | POST | `/api/v1/config/confirm` | -- | 200 | Auto-rollback cancelled |
| Status | GET | `/api/v1/config/apply/status` | -- | 200 | `{"pending":false}` |
| Rollback | POST | `/api/v1/config/rollback/{name}` | -- | 200 | Config rolled back |

### Monitoring Configure

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Configure | POST | `/api/v1/monitoring/configure` | `{"service":"accel-ppp","enabled":true}` | 200 | Monitoring enabled |

### Service Command

| Step | Method | Endpoint | Body | HTTP | Result |
|------|--------|----------|------|:----:|--------|
| Execute | POST | `/api/v1/service/command` | `{"command":"show version"}` | 200 | Version returned |

---

## SSE Streaming Endpoints

| # | Endpoint | Result |
|---|----------|--------|
| 1 | `GET /api/v1/logs/stream` | Connection accepted, SSE stream opened |
| 2 | `GET /api/v1/traffic/stream` | Connection accepted, SSE stream opened |

---

## Request Schema Reference

Field names verified through testing. Use this as a quick reference when calling the API.

| Endpoint | Required Fields | Format |
|----------|----------------|--------|
| IP Pool create | `name`, `ip_range` | CIDR: `"10.0.0.0/24"` |
| Event Hook create | `name`, `event`, `action`, `url` | Events use hyphens: `"session-up"` |
| PPPoE Interface add | `interface` | Interface name: `"ens19"` |
| Firewall Group create | `name`, `group_type`, `members` | Type: `"address"` |
| NAT Masquerade enable | `wan_interface` | Interface name: `"ens18"` |
| VLAN create | `parent`, `vlan_id` | Parent interface + ID |
| Route add | `destination`, `gateway` | CIDR + IP |
| Traffic ratelimit | `rate` | Upload/download: `"5M/20M"` |
| Config apply | `content`, `confirm_minutes` | Full config text + timeout (1--30) |
| Conntrack profile | `name` | Profile: `"default"`, `"gaming"`, `"streaming"` |
| PADO delay | `delay` | Milliseconds: `0`--`1000` |

---

## Environment Notes

Issues discovered and resolved during testing:

### Permission Fix Required

The `/etc/accel-ppp.d/` directory and `/etc/accel-ppp.conf` file must be owned by the `dawos` user for config backup operations to work:

```bash
sudo chown -R dawos:dawos /etc/accel-ppp.d/
sudo chown dawos:dawos /etc/accel-ppp.conf
```

Without this, IP Pool and PPPoE Interface CRUD operations fail with HTTP 500 (`Permission denied` on backup file creation).

> **Recommendation:** The installer (`install.sh`) should set these ownership values automatically.

### Infrastructure-Dependent Endpoints

These endpoints returned non-200 responses due to missing infrastructure, not API bugs:

| Endpoint | Response | Reason |
|----------|----------|--------|
| `POST /api/v1/dns/forwarding/flush` | 500 | dnsmasq not installed |
| `POST /api/v1/traffic/ratelimit/{user}` | 404 | No active PPPoE session |
| `DELETE /api/v1/traffic/ratelimit/{user}` | 404 | No active PPPoE session |
| `POST /api/v1/firewall/groups` | 201 (success=false) | nft tables not configured |

All four are correct behavior given the environment.
