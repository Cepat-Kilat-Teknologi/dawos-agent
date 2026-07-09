# Input Validation Reference

This document describes the input validation strategy used by DawOS Agent
to protect against malformed data and shell injection attacks.

---

## Validation Strategy

DawOS Agent validates all user-supplied input through two independent layers:

1. **Pydantic model validation** -- Request fields are validated against
   type constraints and regex patterns before reaching any service logic.
   Invalid input is rejected with HTTP 422 and a descriptive error message.

2. **Shell argument quoting** -- Service modules apply `shlex.quote()` to
   user-supplied values before interpolating them into shell commands. This
   acts as a secondary defense even if a future code change bypasses the
   model-level check.

These two layers operate independently. Pydantic catches the vast majority
of invalid input at the HTTP boundary; `shlex.quote()` neutralises anything
that slips through.

---

## Validation Patterns

The following regex constants are defined in `dawos_agent/models/schemas.py`
and referenced by request model fields throughout the codebase.

| Pattern | Regex | Accepts |
|---------|-------|---------|
| `SAFE_NAME` | `^[a-zA-Z0-9._@-]+$` | Usernames, hook names, pool names, event types |
| `SAFE_IFACE` | `^[a-zA-Z0-9._-]+$` | Interface names, zone names, group names |
| `SAFE_MAC` | `^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$` | MAC addresses (colon-separated) |
| `SAFE_RATE` | `^[0-9]+[KMGkmg]?/[0-9]+[KMGkmg]?$` | Rate limit strings (`5M/20M`) |
| `SAFE_IP` | `^[0-9A-Fa-f.:/%]+$` | IPv4/IPv6 addresses, CIDR notation |
| `SAFE_ROUTE_DST` | `^(default\|[0-9A-Fa-f.:/%]+)$` | Route destinations (`default` or CIDR) |
| `SAFE_DOMAIN` | `^[a-zA-Z0-9._-]+$` | DNS domain names |
| `SAFE_SYSCTL` | `^[a-z0-9_]+$` | Sysctl parameter keys |
| `SAFE_OPTIONS` | `^[a-zA-Z0-9._,=/ -]*$` | PPPoE interface options (allows empty) |
| `SAFE_ACCEL_CMD` | `^[a-zA-Z0-9 ._=:,/-]+$` | accel-cmd command arguments |
| `SAFE_ELEMENT` | `^[0-9A-Fa-f.:/-]+$` | Firewall group elements (IPs, CIDRs, ports) |

---

## Per-Endpoint Validation Rules

### Session Management

| Model | Field | Constraint |
|-------|-------|------------|
| `TerminateRequest` | `username` | `SAFE_NAME` pattern |
| `TerminateRequest` | `ifname` | `SAFE_IFACE` pattern |
| `RestartSessionRequest` | `username` | `SAFE_NAME` pattern |
| `DropByMacRequest` | `mac` | `SAFE_MAC` pattern |

### Configuration

| Model | Field | Constraint |
|-------|-------|------------|
| `ConfigUpdateRequest` | `content` | min 10 chars, must contain `[` section header |
| `GuardedApplyRequest` | `content` | min 10 chars, must contain `[` section header |
| `CommandRequest` | `command` | `SAFE_ACCEL_CMD` pattern |

### Network Interfaces

| Model | Field | Constraint |
|-------|-------|------------|
| `InterfaceConfigRequest` | `address` | `SAFE_IP` pattern |
| `InterfaceConfigRequest` | `remove_address` | `SAFE_IP` pattern |
| `InterfaceConfigRequest` | `mtu` | integer, 68 -- 65535 |
| `InterfaceConfigRequest` | `state` | `up` or `down` only |

### VLANs

| Model | Field | Constraint |
|-------|-------|------------|
| `VlanCreateRequest` | `parent` | `SAFE_IFACE` pattern |
| `VlanCreateRequest` | `vlan_id` | integer, 1 -- 4094 |
| `VlanCreateRequest` | `address` | `SAFE_IP` pattern |
| `VlanStateRequest` | `state` | `up` or `down` only |

### Routes

| Model | Field | Constraint |
|-------|-------|------------|
| `RouteAddRequest` | `destination` | `SAFE_ROUTE_DST` pattern |
| `RouteAddRequest` | `gateway` | `SAFE_IP` pattern |
| `RouteAddRequest` | `device` | `SAFE_IFACE` pattern |
| `RouteAddRequest` | `metric` | integer >= 0 |
| `RouteDeleteRequest` | `destination` | `SAFE_ROUTE_DST` pattern |
| `RouteDeleteRequest` | `gateway` | `SAFE_IP` pattern |

### DNS

| Model | Field | Constraint |
|-------|-------|------------|
| `DnsUpdateRequest` | `nameservers` | 1--3 items, each validated against `SAFE_IP` |
| `DnsUpdateRequest` | `search_domains` | each validated against `SAFE_DOMAIN` |
| `DnsForwardingSetRequest` | `servers` | 1--5 items, each validated against `SAFE_IP` |
| `DnsForwardingSetRequest` | `cache_size` | integer, 0 -- 100000 |

### NAT and Firewall

| Model | Field | Constraint |
|-------|-------|------------|
| `NatMasqueradeRequest` | `wan_interface` | `SAFE_IFACE` pattern |
| `NatEgressSetRequest` | `target` | `SAFE_IP` pattern |
| `NatEgressSetRequest` | `public_ip` | `SAFE_IP` pattern |
| `NatPublicIpRequest` | `public_ip` | `SAFE_IP` pattern |
| `NatPublicIpRequest` | `interface` | `SAFE_IFACE` pattern (allows empty for auto-detect) |
| `BoxEgressRequest` | `action` | `on` or `off` only |
| `SysctlUpdateRequest` | `ip_forward` | boolean |
| `SysctlUpdateRequest` | `ip6_forward` | boolean |

### PPPoE

| Model | Field | Constraint |
|-------|-------|------------|
| `PppoeAddRequest` | `interface` | `SAFE_IFACE` pattern |
| `PppoeAddRequest` | `options` | `SAFE_OPTIONS` pattern (allows empty) |
| `MacFilterRequest` | `mac` | `SAFE_MAC` pattern |
| `RateLimitRequest` | `rate` | `SAFE_RATE` pattern |
| `SetLimitsRequest` | `max_sessions` | integer >= 0 |
| `SetLimitsRequest` | `max_starting` | integer >= 0 |
| `SetPadoDelayRequest` | `delay` | integer >= 0 |
| `SetPadoDelayRequest` | `min_sessions` | integer >= 0 |

### IP Pool

| Model | Field | Constraint |
|-------|-------|------------|
| `AddPoolRequest` | `name` | `SAFE_NAME` pattern |
| `AddPoolRequest` | `ip_range` | `SAFE_IP` pattern |

### Conntrack

| Model | Field | Constraint |
|-------|-------|------------|
| `ConntrackUpdateRequest` | `max_value` | integer >= 16384 |
| `ConntrackTableSizeRequest` | `size` | integer, 16384 -- 50000000 |
| `ConntrackTimeoutRequest` | `key` | `SAFE_SYSCTL` pattern |
| `ConntrackTimeoutRequest` | `seconds` | integer >= 1 |
| `ConntrackProfileRequest` | `name` | `default`, `gaming`, or `streaming` only |

### Event Handler

| Model | Field | Constraint |
|-------|-------|------------|
| `EventHookRequest` | `name` | `SAFE_NAME` pattern |
| `EventHookRequest` | `event` | `SAFE_NAME` pattern |
| `FireEventRequest` | `event` | `SAFE_NAME` pattern |

### Task Scheduler

| Model | Field | Constraint |
|-------|-------|------------|
| `SchedulerJobRequest` | `name` | `SAFE_NAME` pattern |
| `SchedulerJobRequest` | `interval_seconds` | integer >= 10 |

### Zone Firewall

| Model | Field | Constraint |
|-------|-------|------------|
| `CreateZoneRequest` | `name` | `SAFE_IFACE` pattern |
| `CreateZoneRequest` | `interfaces` | each validated against `SAFE_IFACE` |

### Firewall Groups

| Model | Field | Constraint |
|-------|-------|------------|
| `CreateGroupRequest` | `name` | `SAFE_IFACE` pattern |
| `CreateGroupRequest` | `group_type` | `address`, `network`, or `port` only |
| `CreateGroupRequest` | `elements` | each validated against `SAFE_ELEMENT` |
| `AddMembersRequest` | `elements` | 1+ items, each validated against `SAFE_ELEMENT` |

### VRRP

| Model | Field | Constraint |
|-------|-------|------------|
| `VrrpFailoverRequest` | `group` | `SAFE_NAME` pattern |

### Monitoring

| Model | Field | Constraint |
|-------|-------|------------|
| `ConfigureExporterRequest` | `service` | `SAFE_IFACE` pattern |

---

## Intentionally Unvalidated Fields

Some fields accept free-form input by design because their purpose requires
arbitrary content:

| Model | Field | Reason |
|-------|-------|--------|
| `SchedulerJobRequest` | `command` | Admin-defined shell command |
| `EventHookRequest` | `action` | Webhook URL or shell command |
| `ConfigUpdateRequest` | `content` | Full accel-ppp config text (has structural validator) |
| `GuardedApplyRequest` | `content` | Same as above, with rollback timer |

---

## Shell Argument Quoting

The following service modules apply `shlex.quote()` to user-supplied values
before shell interpolation, regardless of whether Pydantic validation passed:

| Service | Quoted Fields |
|---------|---------------|
| `services/accel.py` | `username`, `ifname`, `rate`, `mac` |
| `services/monitoring.py` | `service` |
| `services/zone_firewall.py` | `zone`, `name` |
| `services/firewall_groups.py` | `name`, `elements` (per item) |
| `services/network.py` | `name` (interface) |

---

## Path Parameters

Path parameters such as `/zones/{zone}` and `/firewall/groups/{name}` are
not part of the Pydantic request body, so they bypass model-level validation.
For these parameters, `shlex.quote()` in the service layer is the sole
defense against injection. The affected path parameters are:

- `/api/v1/zones/{zone}`
- `/api/v1/firewall/groups/{name}`
- `/api/v1/firewall/groups/{name}/members`
- `/api/v1/monitoring/metrics/{service}`
- `/api/v1/monitoring/restart/{service}`
- `/api/v1/network/interfaces/{name}`
- `/api/v1/network/vlans/{name}`
- `/api/v1/pppoe/interfaces/{name}`
- `/api/v1/firewall/nat/egress/{customer_ip}`
- `/api/v1/firewall/nat/public-ip/{public_ip}`

---

## Error Responses

When validation fails, the API returns HTTP 422 with a JSON body describing
the specific field and constraint that was violated:

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["body", "username"],
      "msg": "String should match pattern '^[a-zA-Z0-9._@-]+$'",
      "input": "user;rm -rf /",
      "ctx": {"pattern": "^[a-zA-Z0-9._@-]+$"}
    }
  ]
}
```

Service-level validation errors (e.g. unknown profile name, duplicate entry)
return HTTP 400 with `{"detail": "<message>"}`.
