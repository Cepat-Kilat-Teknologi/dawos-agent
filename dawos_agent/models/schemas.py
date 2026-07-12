"""Pydantic request and response models for the dawos-agent REST API.

Every router in the application imports its data-transfer objects from this
module.  Models are organised by feature domain and follow a consistent
naming convention:

* ``*Response`` — returned to the caller in a JSON body.
* ``*Request`` — accepted from the caller as a JSON body.
* Plain names (``Session``, ``RouteEntry``, …) — embedded sub-models
  composed into larger response objects.

All models inherit from :class:`pydantic.BaseModel`; enumerations use
:class:`enum.Enum` mixed with :class:`str` for automatic JSON
serialisation.
"""

# pylint: disable=too-many-lines,invalid-name

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from ..constants import (
    CONNTRACK_RECOMMENDED_MIN,
)
from ..constants import (
    RE_SAFE_ACCEL_CMD as _RE_SAFE_ACCEL_CMD,
)
from ..constants import (
    RE_SAFE_DOMAIN as _RE_SAFE_DOMAIN,
)
from ..constants import (
    RE_SAFE_ELEMENT as _RE_SAFE_ELEMENT,
)
from ..constants import (
    RE_SAFE_IFACE as _RE_SAFE_IFACE,
)
from ..constants import (
    RE_SAFE_IP as _RE_SAFE_IP,
)
from ..constants import (
    RE_SAFE_MAC as _RE_SAFE_MAC,
)
from ..constants import (
    RE_SAFE_NAME as _RE_SAFE_NAME,
)
from ..constants import (
    RE_SAFE_OPTIONS as _RE_SAFE_OPTIONS,
)
from ..constants import (
    RE_SAFE_RATE as _RE_SAFE_RATE,
)
from ..constants import (
    RE_SAFE_ROUTE_DST as _RE_SAFE_ROUTE_DST,
)
from ..constants import (
    RE_SAFE_SYSCTL as _RE_SAFE_SYSCTL,
)

# Shell-safety regex patterns (canonical definitions in ``constants.py``)
# are re-exported here under their historical ``_RE_SAFE_*`` names and
# applied via ``pattern=`` on ``Field``/``@field_validator`` to reject shell
# metacharacters in request bodies before they reach a subprocess.


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response payload for the ``GET /health`` liveness probe.

    Returned by the unauthenticated health endpoint so load-balancers
    and orchestrators can verify the agent is alive and identify which
    BNG node responded.

    Attributes:
        status: Fixed string ``"ok"`` indicating the process is healthy.
        node_name: Hostname or user-defined label of this BNG node.
        version: Semantic version of the running dawos-agent package.
        uptime_seconds: Wall-clock seconds since the agent process started.
        timestamp: UTC timestamp of the health-check response.
    """

    status: str = "ok"
    node_name: str
    version: str
    uptime_seconds: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReadinessResponse(BaseModel):
    """Response payload for the ``GET /health/ready`` readiness probe.

    Checks whether the agent can communicate with the accel-ppp daemon.
    Returns HTTP 200 when ready, HTTP 503 when one or more dependencies
    are unreachable.

    Attributes:
        ready: True when all dependency checks pass.
        checks: Per-dependency results (service name, reachable flag, detail).
    """

    ready: bool
    checks: list[dict]


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class CpuInfo(BaseModel):
    """Snapshot of CPU utilisation metrics.

    Attributes:
        count: Number of logical CPU cores available.
        percent: Current aggregate CPU usage as a percentage (0–100).
        load_avg: System load averages for the last 1, 5, and 15 minutes.
    """

    count: int
    percent: float
    load_avg: list[float] = Field(description="1/5/15 min load average")


class MemoryInfo(BaseModel):
    """Snapshot of physical memory usage.

    Attributes:
        total_mb: Total installed RAM in megabytes.
        used_mb: RAM currently in use (excluding buffers/cache) in MB.
        available_mb: RAM available for new allocations in MB.
        percent: Memory utilisation as a percentage (0–100).
    """

    total_mb: int
    used_mb: int
    available_mb: int
    percent: float


class DiskInfo(BaseModel):
    """Snapshot of root filesystem disk usage.

    Attributes:
        total_gb: Total disk capacity in gigabytes.
        used_gb: Space consumed in gigabytes.
        free_gb: Space available in gigabytes.
        percent: Disk utilisation as a percentage (0–100).
    """

    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class NetworkInterface(BaseModel):
    """Summary of a single network interface for the system-info response.

    Attributes:
        name: Interface name (e.g. ``eth0``, ``lo``).
        addresses: List of assigned IP addresses (IPv4 and/or IPv6).
        is_up: Whether the interface is operationally up.
    """

    name: str
    addresses: list[str]
    is_up: bool


class SystemInfoResponse(BaseModel):
    """Comprehensive system information for the BNG node.

    Aggregates hardware, OS, and network details into a single response
    so callers can inventory and monitor a fleet of nodes.

    Attributes:
        hostname: System hostname.
        os: Operating system description (e.g. ``"Ubuntu 22.04"``).
        kernel: Kernel version string.
        arch: CPU architecture (e.g. ``"x86_64"``).
        cpu: Current CPU utilisation metrics.
        memory: Current memory utilisation metrics.
        disk: Current root-filesystem disk metrics.
        interfaces: List of network interfaces with addresses and state.
        boot_time: UTC timestamp of the last system boot.
    """

    hostname: str
    os: str
    kernel: str
    arch: str
    cpu: CpuInfo
    memory: MemoryInfo
    disk: DiskInfo
    interfaces: list[NetworkInterface]
    boot_time: datetime


class MetricsResponse(BaseModel):
    """Lightweight real-time metrics snapshot for monitoring dashboards.

    A trimmed-down variant of :class:`SystemInfoResponse` containing only
    the resource-utilisation fields that change frequently.

    Attributes:
        cpu: Current CPU utilisation metrics.
        memory: Current memory utilisation metrics.
        disk: Current disk utilisation metrics.
        timestamp: UTC timestamp when the snapshot was captured.
    """

    cpu: CpuInfo
    memory: MemoryInfo
    disk: DiskInfo
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# accel-ppp Service
# ---------------------------------------------------------------------------


class ServiceAction(str, Enum):
    """Allowed lifecycle actions for the accel-ppp systemd service."""

    start = "start"
    stop = "stop"
    restart = "restart"
    reload = "reload"


class ServiceStatus(str, Enum):
    """Observed runtime state of the accel-ppp service."""

    running = "running"
    stopped = "stopped"
    unknown = "unknown"


class ServiceStatusResponse(BaseModel):
    """Current status of the accel-ppp systemd service.

    Attributes:
        name: Systemd unit name (e.g. ``"accel-ppp"``).
        status: Observed state of the service.
        pid: Main process ID when running, ``None`` otherwise.
        uptime: Human-readable uptime string (e.g. ``"3d 4h"``).
        version: accel-ppp version string if available.
    """

    name: str
    status: ServiceStatus
    pid: int | None = None
    uptime: str | None = None
    version: str | None = None


class ServiceActionResponse(BaseModel):
    """Result of a service lifecycle action (start/stop/restart/reload).

    Attributes:
        action: The action that was requested.
        success: Whether the action completed without error.
        message: Human-readable description of the outcome or error.
    """

    action: ServiceAction
    success: bool
    message: str


class ShutdownMode(str, Enum):
    """Shutdown strategy for the accel-ppp daemon.

    Attributes:
        soft: Drain mode — stop accepting new connections, wait for all
            existing sessions to disconnect naturally, then exit.  Best
            for planned maintenance windows.
        hard: Immediate exit — drop all sessions and terminate now.
            Use only in emergencies.
    """

    soft = "soft"
    hard = "hard"


class ShutdownRequest(BaseModel):
    """Request to initiate accel-ppp daemon shutdown.

    Attributes:
        mode: Shutdown strategy — ``soft`` (drain) or ``hard`` (immediate).
        confirm: Safety flag — must be ``True`` to execute.  Prevents
            accidental shutdown from malformed or exploratory requests.
    """

    mode: ShutdownMode = Field(
        ShutdownMode.soft,
        description="Shutdown strategy: 'soft' (drain) or 'hard' (immediate)",
    )
    confirm: bool = Field(
        False,
        description="Must be true to execute — safety guard against accidental shutdown",
    )


class ShutdownResponse(BaseModel):
    """Result of a shutdown or shutdown-cancel operation.

    Attributes:
        success: Whether the command was accepted by accel-ppp.
        mode: The shutdown mode that was applied (``soft``, ``hard``,
            or ``cancel``).
        message: Human-readable description of the outcome.
        active_sessions: Number of sessions that were active at the
            time the request was processed.
    """

    success: bool
    mode: str
    message: str
    active_sessions: int


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class Session(BaseModel):
    """Represents a single PPPoE/PPTP/L2TP subscriber session.

    Field names with hyphens (``calling-sid``, ``rate-limit``, etc.) are
    mapped to Python-safe attribute names via Pydantic aliases.  The model
    accepts both the alias and the Python name thanks to
    ``populate_by_name``.

    Attributes:
        ifname: Virtual interface name assigned to the session (e.g. ``ppp0``).
        username: Subscriber's RADIUS/PAP/CHAP authentication username.
        ip: IPv4 address assigned to the session.
        calling_sid: Calling-Station-Id (typically the subscriber's MAC address).
        rate_limit: Applied bandwidth shaping rule (e.g. ``"5M/20M"``), empty
            if none.
        type: Session type (``pppoe``, ``pptp``, ``l2tp``, etc.).
        state: Session state as reported by accel-ppp (``active``, ``starting``,
            ``finishing``).
        uptime: Human-readable session duration string.
        rx_bytes: Total bytes received by the subscriber since session start.
        tx_bytes: Total bytes transmitted to the subscriber since session start.
    """

    ifname: str = ""
    username: str = ""
    ip: str = ""
    calling_sid: str = Field("", alias="calling-sid")
    rate_limit: str = Field("", alias="rate-limit")
    type: str = ""
    state: str = ""
    uptime: str = ""
    rx_bytes: str = Field("", alias="rx-bytes")
    tx_bytes: str = Field("", alias="tx-bytes")

    model_config = {"populate_by_name": True}


class SessionListResponse(BaseModel):
    """Paginated list of active subscriber sessions.

    Attributes:
        count: Total number of sessions in the list.
        sessions: Ordered list of :class:`Session` objects.
    """

    count: int
    sessions: list[Session]


class SessionStatsResponse(BaseModel):
    """Aggregated session statistics from ``accel-cmd show stat``.

    Attributes:
        active: Number of sessions in the ``active`` state.
        starting: Number of sessions currently negotiating.
        finishing: Number of sessions in the teardown phase.
        cpu_percent: CPU usage of the accel-ppp process as a percentage.
        pool_used: Number of IP addresses currently leased from the pool.
        pool_total: Total IP addresses available in the pool.
        uptime: accel-ppp daemon uptime string.
    """

    active: int = 0
    starting: int = 0
    finishing: int = 0
    cpu_percent: float = 0.0
    pool_used: int = 0
    pool_total: int = 0
    uptime: str = ""


class TerminateRequest(BaseModel):
    """Request to forcibly disconnect one or more subscriber sessions.

    At least one of ``username`` or ``ifname`` must be provided to
    identify the target session(s).

    Attributes:
        username: Terminate all sessions for this username.
        ifname: Terminate the session on this specific interface.
    """

    username: str | None = Field(None, pattern=_RE_SAFE_NAME)
    ifname: str | None = Field(None, pattern=_RE_SAFE_IFACE)


class TerminateResponse(BaseModel):
    """Result of a session termination request.

    Attributes:
        success: Whether the termination command executed without error.
        message: Human-readable outcome description.
    """

    success: bool
    message: str


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ConfigResponse(BaseModel):
    """Current accel-ppp configuration file content.

    Attributes:
        path: Absolute filesystem path to the configuration file.
        content: Raw text content of the configuration file.
        last_modified: UTC timestamp of the file's last modification.
    """

    path: str
    content: str
    last_modified: datetime | None = None


class ConfigUpdateRequest(BaseModel):
    """Request to overwrite the accel-ppp configuration file.

    Attributes:
        content: New configuration file content to write.
        restart_service: If ``True``, restart the accel-ppp service after
            writing the new configuration.
        backup: If ``True`` (default), create a timestamped backup of the
            current configuration before overwriting.
    """

    content: str = Field(
        min_length=10,
        description="New configuration file content to write",
    )
    restart_service: bool = False
    backup: bool = True

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        """Reject empty or trivially short configuration content."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Config content must not be empty or whitespace-only")
        if "[" not in stripped:
            raise ValueError(
                "Config content must contain at least one section header (e.g. [modules])"
            )
        return value


class ConfigUpdateResponse(BaseModel):
    """Result of a configuration update operation.

    Attributes:
        success: Whether the write (and optional restart) succeeded.
        message: Human-readable outcome or error description.
        backup_path: Filesystem path to the backup file, if one was created.
    """

    success: bool
    message: str
    backup_path: str | None = None


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class CommandRequest(BaseModel):
    """Request to execute an arbitrary ``accel-cmd`` command.

    Attributes:
        command: Arguments to pass to ``accel-cmd`` (e.g. ``"show stat"``).
    """

    command: str = Field(
        description="accel-cmd arguments, e.g. 'show stat'",
        pattern=_RE_SAFE_ACCEL_CMD,
    )


class CommandResponse(BaseModel):
    """Result of an ``accel-cmd`` invocation.

    Attributes:
        success: Whether the command exited with a zero return code.
        output: Raw stdout/stderr output from the command.
        command: Echo of the command string that was executed.
    """

    success: bool
    output: str
    command: str


# ---------------------------------------------------------------------------
# Network Interfaces
# ---------------------------------------------------------------------------


class InterfaceAddress(BaseModel):
    """A single IP address assigned to a network interface.

    Attributes:
        family: Address family — ``"inet"`` for IPv4, ``"inet6"`` for IPv6.
        address: The IP address string (without prefix length).
        prefix_len: CIDR prefix length (e.g. 24 for a /24 subnet).
        broadcast: Broadcast address, if applicable.
        scope: Kernel scope (``global``, ``link``, ``host``).
    """

    family: str = Field(description="inet or inet6")
    address: str
    prefix_len: int
    broadcast: str | None = None
    scope: str = ""


class InterfaceDetail(BaseModel):
    """Detailed information about a single network interface.

    Attributes:
        name: Interface name (e.g. ``eth0``, ``ppp0``).
        index: Kernel interface index number.
        mac_address: Hardware (MAC) address.
        mtu: Maximum Transmission Unit in bytes.
        state: Operational state (``UP``, ``DOWN``, or ``UNKNOWN``).
        flags: List of interface flags (e.g. ``["UP", "BROADCAST"]``).
        addresses: IP addresses assigned to this interface.
        link_type: Link layer type (``ether``, ``vlan``, ``ppp``, ``loopback``).
    """

    name: str
    index: int = 0
    mac_address: str = ""
    mtu: int = 1500
    state: str = Field("unknown", description="UP, DOWN, or UNKNOWN")
    flags: list[str] = []
    addresses: list[InterfaceAddress] = []
    link_type: str = Field("", description="ether, vlan, ppp, loopback")


class InterfaceListResponse(BaseModel):
    """List of all network interfaces on the node.

    Attributes:
        count: Total number of interfaces returned.
        interfaces: Ordered list of :class:`InterfaceDetail` objects.
    """

    count: int
    interfaces: list[InterfaceDetail]


class InterfaceConfigRequest(BaseModel):
    """Request to modify a network interface's configuration.

    All fields are optional — only the provided fields are applied.

    Attributes:
        address: IP address in CIDR notation to add (e.g. ``"10.0.0.1/24"``).
        remove_address: IP address in CIDR notation to remove.
        mtu: New MTU value to set.
        state: Desired operational state (``"up"`` or ``"down"``).
    """

    address: str | None = Field(
        None,
        description="CIDR notation, e.g. 10.0.0.1/24",
        pattern=_RE_SAFE_IP,
    )
    remove_address: str | None = Field(
        None,
        description="CIDR address to remove",
        pattern=_RE_SAFE_IP,
    )
    mtu: int | None = Field(None, ge=68, le=65535, description="MTU value 68-65535")
    state: str | None = Field(
        None,
        description="up or down",
        pattern=r"^(up|down)$",
    )


class InterfaceConfigResponse(BaseModel):
    """Result of an interface configuration change.

    Attributes:
        success: Whether the change was applied successfully.
        message: Human-readable outcome or error description.
        interface: Name of the interface that was modified.
    """

    success: bool
    message: str
    interface: str


class InterfaceThroughput(BaseModel):
    """Byte and rate counters for a single network interface.

    Attributes:
        name: Interface name (e.g. ``eth0``).
        rx_bytes: Cumulative bytes received since boot.
        tx_bytes: Cumulative bytes transmitted since boot.
        rx_bps: Receive rate in bits per second (0 for single-sample reads).
        tx_bps: Transmit rate in bits per second (0 for single-sample reads).
    """

    name: str
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_bps: float = 0.0
    tx_bps: float = 0.0


class ThroughputResponse(BaseModel):
    """Aggregate and per-interface throughput counters.

    A single ``GET`` returns cumulative byte counters from
    ``/proc/net/dev``.  The ``rx_bps`` and ``tx_bps`` fields are ``0``
    on a single read — compute the rate by differencing two successive
    responses and dividing by the elapsed time.

    Attributes:
        rx_bytes: Total received bytes across all non-loopback interfaces.
        tx_bytes: Total transmitted bytes across all non-loopback interfaces.
        rx_bps: Aggregate receive rate in bits per second (0 for a single read).
        tx_bps: Aggregate transmit rate in bits per second (0 for a single read).
        interfaces: Per-interface breakdown.
    """

    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_bps: float = 0.0
    tx_bps: float = 0.0
    interfaces: list[InterfaceThroughput] = Field(default_factory=list)


class VlanCreateRequest(BaseModel):
    """Request to create a new 802.1Q VLAN sub-interface.

    Attributes:
        parent: Parent physical interface (e.g. ``"eth0"``).
        vlan_id: 802.1Q VLAN tag, valid range 1–4094.
        address: Optional IP address in CIDR notation to assign immediately.
    """

    parent: str = Field(
        description="Parent interface, e.g. eth0", pattern=_RE_SAFE_IFACE
    )
    vlan_id: int = Field(ge=1, le=4094, description="VLAN ID 1-4094")
    address: str | None = Field(
        None,
        description="Optional IP in CIDR notation",
        pattern=_RE_SAFE_IP,
    )


class VlanDeleteResponse(BaseModel):
    """Result of a VLAN sub-interface deletion.

    Attributes:
        success: Whether the VLAN interface was removed.
        message: Human-readable outcome description.
        name: Name of the deleted interface (e.g. ``"eth0.100"``).
    """

    success: bool
    message: str
    name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class RouteEntry(BaseModel):
    """A single entry from the kernel routing table.

    Attributes:
        destination: Route destination — ``"default"`` or a CIDR prefix.
        gateway: Next-hop gateway address, if any.
        device: Outgoing network interface name.
        protocol: Route protocol (``kernel``, ``boot``, ``static``, ``bgp``, etc.).
        scope: Route scope (``global``, ``link``, ``host``).
        metric: Route metric / preference value.
        source: Preferred source address for this route.
    """

    destination: str = Field(description="'default' or CIDR notation")
    gateway: str | None = None
    device: str = ""
    protocol: str = ""
    scope: str = ""
    metric: int | None = None
    source: str | None = Field(None, description="Preferred source address")


class RouteListResponse(BaseModel):
    """List of kernel routing table entries.

    Attributes:
        count: Total number of routes returned.
        routes: Ordered list of :class:`RouteEntry` objects.
    """

    count: int
    routes: list[RouteEntry]


class RouteAddRequest(BaseModel):
    """Request to add a static route to the kernel routing table.

    Attributes:
        destination: Target network in CIDR notation, or ``"default"``.
        gateway: Next-hop gateway IP address.
        device: Optional outgoing interface to bind the route to.
        metric: Optional route metric / preference value.
    """

    destination: str = Field(
        description="CIDR or 'default'",
        pattern=_RE_SAFE_ROUTE_DST,
    )
    gateway: str = Field(pattern=_RE_SAFE_IP)
    device: str | None = Field(None, pattern=_RE_SAFE_IFACE)
    metric: int | None = Field(None, ge=0)


class RouteDeleteRequest(BaseModel):
    """Request to remove a route from the kernel routing table.

    Attributes:
        destination: Target network in CIDR notation, or ``"default"``.
        gateway: Optional gateway to disambiguate when multiple routes
            exist for the same destination.
    """

    destination: str = Field(
        description="CIDR or 'default'",
        pattern=_RE_SAFE_ROUTE_DST,
    )
    gateway: str | None = Field(None, pattern=_RE_SAFE_IP)


class RouteResponse(BaseModel):
    """Generic success/failure response for route operations.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
    """

    success: bool
    message: str


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------


class DnsConfig(BaseModel):
    """Current DNS resolver configuration read from ``/etc/resolv.conf``.

    Attributes:
        nameservers: Ordered list of nameserver IP addresses.
        search_domains: DNS search domain suffixes.
    """

    nameservers: list[str]
    search_domains: list[str] = []


class DnsUpdateRequest(BaseModel):
    """Request to overwrite the system DNS resolver configuration.

    Attributes:
        nameservers: One to three nameserver IP addresses to write.
        search_domains: Optional search domain suffixes.
    """

    nameservers: list[str] = Field(min_length=1, max_length=3)
    search_domains: list[str] = []

    @field_validator("nameservers")
    @classmethod
    def _safe_nameservers(cls, val: list[str]) -> list[str]:
        """Reject non-IP characters in nameserver entries."""
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_IP)
        for item in val:
            if not pat.match(item):
                msg = f"Invalid nameserver address: {item!r}"
                raise ValueError(msg)
        return val

    @field_validator("search_domains")
    @classmethod
    def _safe_search_domains(cls, val: list[str]) -> list[str]:
        """Reject unsafe characters in search domain entries."""
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_DOMAIN)
        for item in val:
            if not pat.match(item):
                msg = f"Invalid search domain: {item!r}"
                raise ValueError(msg)
        return val


class DnsResponse(BaseModel):
    """Result of a DNS configuration read or update.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
        config: The resulting DNS configuration after the operation.
    """

    success: bool
    message: str
    config: DnsConfig | None = None


# ---------------------------------------------------------------------------
# Firewall / NAT
# ---------------------------------------------------------------------------


class SysctlStatus(BaseModel):
    """Current state of IP forwarding kernel parameters.

    Attributes:
        ip_forward: Whether IPv4 forwarding is enabled (``net.ipv4.ip_forward``).
        ip6_forward: Whether IPv6 forwarding is enabled (``net.ipv6.conf.all.forwarding``).
    """

    ip_forward: bool
    ip6_forward: bool


class FirewallStatus(BaseModel):
    """High-level firewall status summary.

    Attributes:
        enabled: Whether the firewall subsystem is active.
        backend: Firewall backend in use (``"nftables"`` or ``"iptables"``).
        rules_count: Total number of active firewall rules.
        nat_enabled: Whether NAT/masquerade rules are present.
        sysctl: Current IP forwarding kernel settings, if retrieved.
    """

    enabled: bool
    backend: str = Field("nftables", description="nftables or iptables")
    rules_count: int = 0
    nat_enabled: bool = False
    sysctl: SysctlStatus | None = None


class NatMasqueradeRequest(BaseModel):
    """Request to enable NAT masquerade on a WAN interface.

    Attributes:
        wan_interface: Name of the outbound WAN interface (e.g. ``"eth0"``).
    """

    wan_interface: str = Field(
        description="WAN interface for masquerade, e.g. eth0",
        pattern=_RE_SAFE_IFACE,
    )


class NatMasqueradeResponse(BaseModel):
    """Result of a NAT masquerade enable/disable operation.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
        wan_interface: The WAN interface the operation targeted.
    """

    success: bool
    message: str
    wan_interface: str


class FirewallRulesetResponse(BaseModel):
    """Full nftables ruleset dump.

    Attributes:
        raw_output: Complete output of ``nft list ruleset``.
        rules_count: Total number of individual rules found.
    """

    raw_output: str = Field(description="Full nft list ruleset output")
    rules_count: int = 0


class SysctlUpdateRequest(BaseModel):
    """Request to toggle IP forwarding sysctl parameters.

    Attributes:
        ip_forward: Desired state for IPv4 forwarding.
        ip6_forward: Desired state for IPv6 forwarding.
    """

    ip_forward: bool = True
    ip6_forward: bool = False


class SysctlResponse(BaseModel):
    """Result of a sysctl update operation.

    Attributes:
        success: Whether the sysctl values were applied.
        message: Human-readable outcome description.
        status: The resulting sysctl state after the operation.
    """

    success: bool
    message: str
    status: SysctlStatus


# ---------------------------------------------------------------------------
# VLAN detection
# ---------------------------------------------------------------------------


class VlanInfo(BaseModel):
    """Auto-detected VLAN from kernel (``ip -j -d link show type vlan``)."""

    name: str = Field(description="Interface name, e.g. eth0.100")
    parent: str = Field(description="Parent interface, e.g. eth0")
    vlan_id: int = Field(description="802.1Q VLAN ID")
    protocol: str = Field("802.1Q", description="VLAN protocol")
    state: str = Field(description="Operational state: UP / DOWN / UNKNOWN")
    mac_address: str = ""
    mtu: int = 1500
    addresses: list[InterfaceAddress] = []


class VlanListResponse(BaseModel):
    """List of all kernel-detected 802.1Q VLAN sub-interfaces.

    Attributes:
        count: Number of VLANs detected.
        vlans: List of :class:`VlanInfo` objects.
    """

    count: int
    vlans: list[VlanInfo]


class VlanStateRequest(BaseModel):
    """Request to change a VLAN interface's administrative state.

    Attributes:
        state: Desired state — ``"up"`` or ``"down"``.
    """

    state: str = Field(description="'up' or 'down'", pattern=r"^(up|down)$")


class VlanStateResponse(BaseModel):
    """Result of a VLAN state change operation.

    Attributes:
        success: Whether the state change was applied.
        message: Human-readable outcome description.
        name: VLAN interface name that was modified.
        state: The resulting state after the operation.
    """

    success: bool
    message: str
    name: str
    state: str


# ---------------------------------------------------------------------------
# PPPoE interface binding
# ---------------------------------------------------------------------------


class PppoeInterface(BaseModel):
    """A PPPoE listener interface from accel-ppp.conf ``[pppoe]`` section."""

    name: str = Field(description="Interface name, e.g. eth0.100")
    options: str = Field("", description="Comma-separated options, e.g. padi-limit=0")


class PppoeInterfaceListResponse(BaseModel):
    """List of interfaces bound to the accel-ppp PPPoE listener.

    Attributes:
        count: Number of bound interfaces.
        interfaces: List of :class:`PppoeInterface` objects.
    """

    count: int
    interfaces: list[PppoeInterface]


class PppoeAddRequest(BaseModel):
    """Request to bind a new interface to the accel-ppp PPPoE listener.

    Attributes:
        interface: Network interface name to add (e.g. ``"eth0.100"``).
        options: Optional comma-separated accel-ppp options
            (e.g. ``"padi-limit=0"``).
    """

    interface: str = Field(
        description="Interface name to add, e.g. eth0.100",
        pattern=_RE_SAFE_IFACE,
    )
    options: str = Field(
        "",
        description="Optional: comma-separated options like padi-limit=0",
        pattern=_RE_SAFE_OPTIONS,
    )


class PppoeResponse(BaseModel):
    """Generic result for PPPoE interface binding operations.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
    """

    success: bool
    message: str


# ---------------------------------------------------------------------------
# MAC filter
# ---------------------------------------------------------------------------


class MacFilterListResponse(BaseModel):
    """Current MAC address filter list from accel-ppp.

    Attributes:
        raw_output: Raw ``accel-cmd`` output of the MAC filter table.
        count: Number of MAC entries in the filter.
    """

    raw_output: str
    count: int = 0


class MacFilterRequest(BaseModel):
    """Request to add or remove a MAC address from the filter.

    Attributes:
        mac: MAC address in colon-separated hex format
            (e.g. ``"AA:BB:CC:DD:EE:FF"``).
    """

    mac: str = Field(
        description="MAC address, e.g. AA:BB:CC:DD:EE:FF",
        pattern=_RE_SAFE_MAC,
    )


class MacFilterResponse(BaseModel):
    """Result of a MAC filter modification.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
    """

    success: bool
    message: str


# ---------------------------------------------------------------------------
# Traffic / SSE
# ---------------------------------------------------------------------------


class QueueStats(BaseModel):
    """Traffic-control queue statistics for a subscriber's interface.

    Attributes:
        username: Subscriber's authentication username.
        ifname: PPP interface name (e.g. ``"ppp0"``).
        qdisc: Active queueing discipline (e.g. ``"htb"``, ``"fq_codel"``).
        classes: Raw ``tc class`` output for this interface.
        filters: Raw ``tc filter`` output for this interface.
    """

    username: str
    ifname: str
    qdisc: str = ""
    classes: str = ""
    filters: str = ""


class RateLimitRequest(BaseModel):
    """Request to change a subscriber's bandwidth shaping rule.

    Attributes:
        rate: Bandwidth limit in ``upload/download`` format
            (e.g. ``"5M/20M"`` for 5 Mbps up / 20 Mbps down).
    """

    rate: str = Field(
        description="Rate in up/down format, e.g. '5M/20M'",
        pattern=_RE_SAFE_RATE,
    )


class RateLimitResponse(BaseModel):
    """Result of a rate-limit change operation.

    Attributes:
        success: Whether the rate limit was applied.
        message: Human-readable outcome description.
        username: Subscriber whose rate was changed.
        rate: The rate string that was applied.
    """

    success: bool
    message: str
    username: str = ""
    rate: str = ""


# ---------------------------------------------------------------------------
# Routing — BGP
# ---------------------------------------------------------------------------


class BgpNeighbor(BaseModel):
    """A single BGP peering neighbour.

    Attributes:
        neighbor: Peer IP address.
        remote_as: Remote Autonomous System number.
        state: BGP session state (e.g. ``"Established"``, ``"Idle"``).
        up_down: Duration the session has been in its current state.
        prefixes_received: Number of prefixes received from this peer.
    """

    neighbor: str = ""
    remote_as: str = ""
    state: str = ""
    up_down: str = ""
    prefixes_received: int = 0


class BgpStatusResponse(BaseModel):
    """BGP routing daemon status summary.

    Attributes:
        configured: Whether BGP is configured on this node.
        router_id: Local BGP router ID.
        local_as: Local Autonomous System number.
        neighbors: List of configured BGP peers.
        total_prefixes: Aggregate number of received prefixes.
        raw_output: Raw ``vtysh`` command output for debugging.
    """

    configured: bool
    router_id: str = ""
    local_as: str = ""
    neighbors: list[BgpNeighbor] = []
    total_prefixes: int = 0
    raw_output: str = ""


class BgpRoutesResponse(BaseModel):
    """BGP routing table dump.

    Attributes:
        count: Number of routes in the BGP RIB.
        raw_output: Raw ``vtysh`` route table output.
    """

    count: int = 0
    raw_output: str = ""


# ---------------------------------------------------------------------------
# Routing — OSPF
# ---------------------------------------------------------------------------


class OspfNeighbor(BaseModel):
    """A single OSPF adjacency neighbour.

    Attributes:
        neighbor_id: OSPF router ID of the neighbour.
        priority: Neighbour's DR election priority.
        state: OSPF adjacency state (e.g. ``"Full"``, ``"2-Way"``).
        address: Neighbour's interface IP address.
        interface: Local interface the adjacency is formed on.
    """

    neighbor_id: str = ""
    priority: int = 0
    state: str = ""
    address: str = ""
    interface: str = ""


class OspfStatusResponse(BaseModel):
    """OSPF routing daemon status summary.

    Attributes:
        configured: Whether OSPF is configured on this node.
        router_id: Local OSPF router ID.
        neighbors: List of OSPF adjacencies.
        raw_output: Raw ``vtysh`` command output for debugging.
    """

    configured: bool
    router_id: str = ""
    neighbors: list[OspfNeighbor] = []
    raw_output: str = ""


class OspfRoutesResponse(BaseModel):
    """OSPF routing table dump.

    Attributes:
        count: Number of OSPF-learned routes.
        raw_output: Raw route table output.
    """

    count: int = 0
    raw_output: str = ""


# ---------------------------------------------------------------------------
# Routing — RIP
# ---------------------------------------------------------------------------


class RipRoute(BaseModel):
    """A single RIP routing table entry.

    Attributes:
        code: Route code — ``R(n)`` for RIP-learned, ``C`` for connected.
        network: Destination network in CIDR notation.
        nexthop: Next-hop IP address.
        metric: RIP hop-count metric.
    """

    code: str = Field("", description="R(n) for RIP learned, C for connected")
    network: str = ""
    nexthop: str = ""
    metric: int = 0


class RipStatusResponse(BaseModel):
    """RIP routing daemon status summary.

    Attributes:
        configured: Whether RIP is configured on this node.
        version: RIP protocol version (``"1"`` or ``"2"``).
        networks: List of networks advertised by RIP.
        neighbors: List of RIP neighbour IP addresses.
        raw_output: Raw ``vtysh`` command output for debugging.
    """

    configured: bool
    version: str = ""
    networks: list[str] = []
    neighbors: list[str] = []
    raw_output: str = ""


class RipRoutesResponse(BaseModel):
    """RIP routing table dump.

    Attributes:
        count: Number of RIP routes.
        routes: Parsed list of :class:`RipRoute` entries.
        raw_output: Raw route table output.
    """

    count: int = 0
    routes: list[RipRoute] = []
    raw_output: str = ""


# ---------------------------------------------------------------------------
# Config Checkpoint
# ---------------------------------------------------------------------------


class CheckpointRevision(BaseModel):
    """A single configuration checkpoint (backup) revision.

    Attributes:
        name: Filename of the checkpoint.
        size: File size in bytes.
        created: Human-readable creation timestamp.
        is_checkpoint: ``True`` if this was created by the guarded-apply
            mechanism rather than a manual backup.
    """

    name: str
    size: int = 0
    created: str = ""
    is_checkpoint: bool = False


class CheckpointListResponse(BaseModel):
    """List of available configuration checkpoint revisions.

    Attributes:
        count: Number of revisions available.
        revisions: Ordered list of :class:`CheckpointRevision` objects.
    """

    count: int = 0
    revisions: list[CheckpointRevision] = []


class CheckpointDiffResponse(BaseModel):
    """Unified diff between the running config and a checkpoint.

    Attributes:
        diff: Unified diff output (empty string if no differences).
        changed: ``True`` if the two configurations differ.
    """

    diff: str = ""
    changed: bool = False


class CheckpointRollbackResponse(BaseModel):
    """Result of rolling back to a previous configuration checkpoint.

    Attributes:
        success: Whether the rollback was applied.
        message: Human-readable outcome description.
        safety_backup: Path to the safety backup taken before rollback.
    """

    success: bool
    message: str
    safety_backup: str = ""


class RevisionContentResponse(BaseModel):
    """Content of a specific configuration revision.

    Attributes:
        name: Filename of the revision.
        size: File size in bytes.
        created: ISO-format creation timestamp.
        content: Full text content of the revision file.
    """

    name: str = ""
    size: int = 0
    created: str = ""
    content: str = ""


class RevisionCompareResponse(BaseModel):
    """Unified diff between two named configuration revisions.

    Attributes:
        from_name: Filename of the first (older) revision.
        to_name: Filename of the second (newer) revision.
        diff: Unified diff output (empty string if no differences).
        changed: True if the two revisions differ.
    """

    from_name: str = ""
    to_name: str = ""
    diff: str = ""
    changed: bool = False


class GuardedApplyRequest(BaseModel):
    """Request to apply a new configuration with automatic rollback protection.

    The guarded-apply mechanism saves a checkpoint, writes the new config,
    and restarts accel-ppp.  If the operator does not confirm within
    ``confirm_minutes``, the previous config is automatically restored.

    Attributes:
        content: New configuration file content to apply.
        confirm_minutes: Timeout in minutes (1–30) before auto-rollback.
    """

    content: str = Field(
        min_length=10,
        description="New config content to apply",
    )
    confirm_minutes: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Auto-rollback timeout in minutes (1-30)",
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        """Reject empty or trivially short configuration content."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Config content must not be empty or whitespace-only")
        if "[" not in stripped:
            raise ValueError(
                "Config content must contain at least one section header (e.g. [modules])"
            )
        return value


class GuardedApplyResponse(BaseModel):
    """Result of initiating a guarded configuration apply.

    Attributes:
        success: Whether the new config was written and service restarted.
        message: Human-readable outcome description.
        checkpoint: Name of the checkpoint created before the change.
        confirm_deadline_seconds: Seconds remaining to confirm the change.
    """

    success: bool
    message: str
    checkpoint: str = ""
    confirm_deadline_seconds: int = 0


class ConfirmApplyResponse(BaseModel):
    """Result of confirming a pending guarded configuration change.

    Attributes:
        success: Whether the confirmation was accepted.
        message: Human-readable outcome description.
    """

    success: bool
    message: str


class GuardedStatusResponse(BaseModel):
    """Status of a pending guarded-apply operation.

    Attributes:
        pending: ``True`` if a guarded change is awaiting confirmation.
        checkpoint: Name of the checkpoint that will be restored on timeout.
    """

    pending: bool = False
    checkpoint: str | None = None


# ---------------------------------------------------------------------------
# Firewall validation
# ---------------------------------------------------------------------------


class NftValidateResponse(BaseModel):
    """Result of validating an nftables ruleset for syntax errors.

    Attributes:
        valid: Whether the ruleset passed syntax validation.
        detail: Validation error message if invalid, empty otherwise.
    """

    valid: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Diagnostics (doctor)
# ---------------------------------------------------------------------------


class DiagCheck(BaseModel):
    """A single diagnostic check result from the doctor endpoint.

    Attributes:
        name: Short identifier for the check (e.g. ``"config_syntax"``).
        status: Result verdict — ``"ok"``, ``"warn"``, or ``"fail"``.
        detail: Human-readable explanation of the check outcome.
    """

    name: str
    status: str = Field(description="ok, warn, or fail")
    detail: str = ""


class DiagnosticsResponse(BaseModel):
    """Aggregated results from all diagnostic checks.

    The doctor endpoint runs a battery of self-tests covering config
    syntax, service status, pool utilisation, and more.

    Attributes:
        checks: Individual check results.
        total: Total number of checks executed.
        fails: Number of checks that returned ``"fail"``.
        warns: Number of checks that returned ``"warn"``.
        healthy: ``True`` if no checks failed.
    """

    checks: list[DiagCheck]
    total: int = 0
    fails: int = 0
    warns: int = 0
    healthy: bool = True


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


class LogResponse(BaseModel):
    """A batch of log lines from the accel-ppp or system journal.

    Attributes:
        lines: Individual log line strings.
        count: Number of lines returned.
        source: Log source identifier (e.g. ``"accel-ppp"``).
    """

    lines: list[str]
    count: int = 0
    source: str = "accel-ppp"


# ---------------------------------------------------------------------------
# NAT per-customer egress
# ---------------------------------------------------------------------------


class NatEgressEntry(BaseModel):
    """A single per-customer NAT egress IP mapping.

    Maps a subscriber's private IP to a specific public egress IP for
    outbound traffic, enabling deterministic source NAT.

    Attributes:
        customer_ip: Subscriber's private IP address.
        public_ip: Public IP used for SNAT of this subscriber's traffic.
    """

    customer_ip: str
    public_ip: str


class NatEgressMapResponse(BaseModel):
    """Complete per-customer NAT egress mapping table.

    Attributes:
        entries: List of customer-to-public IP mappings.
        count: Number of active mappings.
    """

    entries: list[NatEgressEntry] = []
    count: int = 0


class NatEgressSetRequest(BaseModel):
    """Request to assign a per-customer public egress IP.

    Attributes:
        target: Customer's private IP address.
        public_ip: Public IP to assign for outbound NAT.
    """

    target: str = Field(description="Customer IP address", pattern=_RE_SAFE_IP)
    public_ip: str = Field(description="Public egress IP", pattern=_RE_SAFE_IP)


class NatEgressResponse(BaseModel):
    """Result of a NAT egress mapping operation.

    Attributes:
        success: Whether the mapping was applied.
        message: Human-readable outcome description.
    """

    success: bool
    message: str


class NatPublicIpRequest(BaseModel):
    """Request to bind/unbind a public IP address on the uplink interface.

    Attributes:
        public_ip: Public IP address to add or remove.
        interface: Uplink interface name; auto-detected if empty.
    """

    public_ip: str = Field(pattern=_RE_SAFE_IP)
    interface: str = Field(
        "",
        description="Uplink interface (auto-detected if empty)",
        pattern=r"^[a-zA-Z0-9._-]*$",
    )


class NatStatusResponse(BaseModel):
    """Comprehensive NAT subsystem status.

    Attributes:
        egress_map: Current per-customer egress IP mappings.
        postrouting_rules: Raw nftables/iptables POSTROUTING chain output.
        bound_ips: Raw output showing secondary IPs bound to the uplink.
    """

    egress_map: list[NatEgressEntry] = []
    postrouting_rules: str = ""
    bound_ips: str = ""


class BoxEgressRequest(BaseModel):
    """Request to toggle box-level egress NAT (masquerade on/off).

    Attributes:
        action: ``"on"`` to enable or ``"off"`` to disable masquerade.
    """

    action: str = Field(description="on or off", pattern=r"^(on|off)$")


class BoxEgressResponse(BaseModel):
    """Result of toggling box-level egress NAT.

    Attributes:
        success: Whether the toggle was applied.
        message: Human-readable outcome description.
        enabled: Resulting state of box-level egress.
    """

    success: bool
    message: str
    enabled: bool = False


# ---------------------------------------------------------------------------
# Conntrack
# ---------------------------------------------------------------------------


class ConntrackResponse(BaseModel):
    """Quick conntrack table health check.

    Attributes:
        current_max: Current ``nf_conntrack_max`` kernel value.
        recommended_min: Minimum recommended value for BNG workloads.
        status: ``"ok"`` if current_max ≥ recommended_min, else ``"warn"``.
        detail: Explanation of the status verdict.
    """

    current_max: int = 0
    recommended_min: int = CONNTRACK_RECOMMENDED_MIN
    status: str = Field("unknown", description="ok or warn")
    detail: str = ""


class ConntrackUpdateRequest(BaseModel):
    """Request to set the ``nf_conntrack_max`` kernel parameter.

    Attributes:
        max_value: New value for ``nf_conntrack_max`` (minimum 16 384).
    """

    max_value: int = Field(ge=16384, description="nf_conntrack_max value")


# ---------------------------------------------------------------------------
# SNMP
# ---------------------------------------------------------------------------


class SnmpStatusResponse(BaseModel):
    """SNMP agent daemon status.

    Attributes:
        running: Whether the SNMP daemon process is active.
        port_open: Whether UDP port 161 is listening.
        detail: Additional diagnostic information.
    """

    running: bool = False
    port_open: bool = False
    detail: str = ""


# ---------------------------------------------------------------------------
# Task Scheduler
# ---------------------------------------------------------------------------


class SchedulerJobRequest(BaseModel):
    """Request to create or update a scheduled recurring job.

    Attributes:
        name: Unique human-readable identifier for the job.
        command: Shell command to execute on each run.
        interval_seconds: Repeat interval (minimum 10 seconds).
        enabled: Whether the job should run on schedule.
    """

    name: str = Field(description="Unique job name", pattern=_RE_SAFE_NAME)
    command: str = Field(description="Shell command to execute")
    interval_seconds: int = Field(ge=10, description="Repeat interval in seconds")
    enabled: bool = True


class SchedulerJobResponse(BaseModel):
    """Details of a single scheduled job.

    Attributes:
        name: Unique job identifier.
        command: Shell command that is executed.
        interval_seconds: Repeat interval in seconds.
        enabled: Whether the job is active.
        last_run: ISO-8601 timestamp of the most recent execution.
        last_result: Return code and output of the last run.
        run_count: Total number of times the job has executed.
    """

    name: str
    command: str = ""
    interval_seconds: int = 0
    enabled: bool = True
    last_run: str | None = None
    last_result: dict | None = None
    run_count: int = 0


class SchedulerListResponse(BaseModel):
    """List of all registered scheduler jobs.

    Attributes:
        count: Number of registered jobs.
        jobs: List of :class:`SchedulerJobResponse` objects.
    """

    count: int = 0
    jobs: list[SchedulerJobResponse] = []


class SchedulerRunResponse(BaseModel):
    """Result of manually triggering a scheduled job.

    Attributes:
        success: Whether the command exited successfully.
        output: Captured stdout/stderr from the command.
        returncode: Process exit code.
        timestamp: ISO-8601 timestamp of the execution.
    """

    success: bool
    output: str = ""
    returncode: int = 0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Conntrack Tuning
# ---------------------------------------------------------------------------


class ConntrackConfigResponse(BaseModel):
    """Detailed conntrack table configuration and utilisation.

    Attributes:
        table_size: Current ``nf_conntrack_max`` value.
        current_count: Number of active connection-tracking entries.
        hash_size: Size of the conntrack hash table (buckets).
        usage_percent: Percentage of the table currently in use.
    """

    table_size: int = 0
    current_count: int = 0
    hash_size: int = 0
    usage_percent: float = 0.0


class ConntrackTableSizeRequest(BaseModel):
    """Request to resize the conntrack table.

    Attributes:
        size: New ``nf_conntrack_max`` value (16 384 – 50 000 000).
    """

    size: int = Field(ge=16384, le=50000000, description="nf_conntrack_max")


class ConntrackTimeoutRequest(BaseModel):
    """Request to update a single conntrack timeout parameter.

    Attributes:
        key: Sysctl timeout key (e.g. ``"tcp_timeout_established"``).
        seconds: New timeout value in seconds.
    """

    key: str = Field(
        description="Timeout key, e.g. tcp_timeout_established",
        pattern=_RE_SAFE_SYSCTL,
    )
    seconds: int = Field(ge=1, description="Timeout in seconds")


class ConntrackTimeoutsResponse(BaseModel):
    """Current conntrack timeout values.

    Attributes:
        timeouts: Mapping of timeout key names to their values in seconds.
    """

    timeouts: dict[str, int] = {}


class ConntrackHelperResponse(BaseModel):
    """A loaded conntrack helper kernel module.

    Attributes:
        module: Kernel module name (e.g. ``"nf_conntrack_ftp"``).
        size: Module memory footprint in bytes.
        used_by: Number of other modules depending on this one.
    """

    module: str
    size: int = 0
    used_by: int = 0


class ConntrackHelpersListResponse(BaseModel):
    """List of loaded conntrack helper kernel modules.

    Attributes:
        count: Number of helper modules loaded.
        helpers: List of :class:`ConntrackHelperResponse` objects.
    """

    count: int = 0
    helpers: list[ConntrackHelperResponse] = []


class ConntrackProfileRequest(BaseModel):
    """Request to apply a pre-defined conntrack tuning profile.

    Profiles adjust multiple timeout and table-size parameters at once
    for common workload patterns.

    Attributes:
        name: Profile name — ``"default"``, ``"gaming"``, or ``"streaming"``.
    """

    name: str = Field(
        description="Profile name: default, gaming, streaming",
        pattern=r"^(default|gaming|streaming)$",
    )


# ---------------------------------------------------------------------------
# BFD
# ---------------------------------------------------------------------------


class BfdPeer(BaseModel):
    """A single Bidirectional Forwarding Detection (BFD) peer.

    Attributes:
        peer: Peer IP address.
        interface: Local interface the BFD session runs over.
        status: Session state (e.g. ``"Up"``, ``"Down"``, ``"Init"``).
        uptime: Duration the session has been in its current state.
    """

    peer: str = ""
    interface: str = ""
    status: str = ""
    uptime: str = ""


class BfdPeersResponse(BaseModel):
    """List of BFD peers and their session states.

    Attributes:
        configured: Whether BFD is configured on this node.
        peers: List of :class:`BfdPeer` objects.
        count: Number of BFD peers.
        raw_output: Raw ``vtysh`` command output for debugging.
    """

    configured: bool
    peers: list[BfdPeer] = []
    count: int = 0
    raw_output: str = ""


class BfdSummaryResponse(BaseModel):
    """BFD subsystem summary.

    Attributes:
        configured: Whether BFD is configured on this node.
        raw_output: Raw ``vtysh`` summary output.
    """

    configured: bool
    raw_output: str = ""


# ---------------------------------------------------------------------------
# DNS Forwarding
# ---------------------------------------------------------------------------


class DnsForwardingStatusResponse(BaseModel):
    """DNS forwarding service status.

    Attributes:
        running: Whether the DNS forwarder daemon is active.
        backend: Forwarder backend name (e.g. ``"dnsmasq"``).
        upstream_count: Number of configured upstream DNS servers.
    """

    running: bool = False
    backend: str = "dnsmasq"
    upstream_count: int = 0


class DnsForwardingConfigResponse(BaseModel):
    """Current DNS forwarding configuration.

    Attributes:
        servers: List of upstream DNS server addresses.
        listen_address: Local address the forwarder listens on.
        cache_size: Maximum number of cached DNS entries.
    """

    servers: list[str] = []
    listen_address: str = ""
    cache_size: int = 150


class DnsForwardingSetRequest(BaseModel):
    """Request to update DNS forwarding configuration.

    Attributes:
        servers: One to five upstream DNS server addresses.
        cache_size: DNS cache size (0 disables caching, max 100 000).
    """

    servers: list[str] = Field(min_length=1, max_length=5)
    cache_size: int = Field(default=1000, ge=0, le=100000)

    @field_validator("servers")
    @classmethod
    def _safe_servers(cls, val: list[str]) -> list[str]:
        """Reject non-IP characters in upstream server entries."""
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_IP)
        for item in val:
            if not pat.match(item):
                msg = f"Invalid server address: {item!r}"
                raise ValueError(msg)
        return val


class DnsForwardingFlushResponse(BaseModel):
    """Result of flushing the DNS forwarder cache.

    Attributes:
        flushed: Whether the cache was successfully cleared.
    """

    flushed: bool = False


# ---------------------------------------------------------------------------
# NTP
# ---------------------------------------------------------------------------


class NtpStatusResponse(BaseModel):
    """NTP synchronisation status from ``chronyc`` or ``ntpstat``.

    Attributes:
        synced: Whether the system clock is synchronised to an NTP source.
        reference: Reference source identifier.
        stratum: NTP stratum level of the current reference.
        system_time_offset: Estimated offset of the system clock.
        last_offset: Offset of the most recent measurement.
        frequency: Clock frequency drift in ppm.
        raw_output: Raw command output for debugging.
    """

    synced: bool = False
    reference: str = ""
    stratum: int = 0
    system_time_offset: str = ""
    last_offset: str = ""
    frequency: str = ""
    raw_output: str = ""


class NtpSource(BaseModel):
    """A single NTP time source.

    Attributes:
        tally: Tally code indicating source status (e.g. ``"*"``, ``"+"``, ``"-"``).
        name: Source hostname or IP address.
        stratum: Stratum level of this source.
        poll: Polling interval in seconds.
        reach: Reachability register (octal).
        detail: Additional source detail string.
    """

    tally: str = ""
    name: str = ""
    stratum: int = 0
    poll: int = 0
    reach: str = ""
    detail: str = ""


class NtpSourcesResponse(BaseModel):
    """List of configured NTP time sources.

    Attributes:
        count: Number of configured sources.
        sources: List of :class:`NtpSource` objects.
        raw_output: Raw command output for debugging.
    """

    count: int = 0
    sources: list[NtpSource] = []
    raw_output: str = ""


# ---------------------------------------------------------------------------
# Session Control (Sprint 2)
# ---------------------------------------------------------------------------


class SessionByIdResponse(BaseModel):
    """Result of looking up a session by its interface name or SID.

    Attributes:
        found: Whether a matching session was located.
        session: Session details as a raw dictionary, or ``None``.
    """

    found: bool = False
    session: dict | None = None


class SessionSnapshotResponse(BaseModel):
    """All active sessions for a specific subscriber username.

    Attributes:
        username: The queried subscriber username.
        found: Whether any sessions were found.
        sessions: List of raw session dictionaries.
        count: Number of sessions found.
    """

    username: str = ""
    found: bool = False
    sessions: list[dict] = []
    count: int = 0


class RestartSessionRequest(BaseModel):
    """Request to disconnect and immediately re-establish a subscriber session.

    Attributes:
        username: PPPoE username of the session to restart.
    """

    username: str = Field(
        ...,
        description="PPPoE username to restart",
        pattern=_RE_SAFE_NAME,
    )


class RestartSessionResponse(BaseModel):
    """Result of a session restart operation.

    Attributes:
        success: Whether the restart completed without error.
        username: The subscriber whose session was restarted.
        previous_interface: Interface name of the terminated session.
        message: Human-readable outcome description.
    """

    success: bool = False
    username: str = ""
    previous_interface: str = ""
    message: str = ""


class DropByMacRequest(BaseModel):
    """Request to disconnect all sessions from a specific MAC address.

    Attributes:
        mac: Calling-Station-Id (MAC address) to match.
    """

    mac: str = Field(
        ...,
        description="MAC address (calling-station-id)",
        pattern=_RE_SAFE_MAC,
    )


class DropByMacResponse(BaseModel):
    """Result of dropping sessions by MAC address.

    Attributes:
        success: Whether the operation completed without error.
        dropped: Number of sessions that were terminated.
        message: Human-readable outcome description.
    """

    success: bool = False
    dropped: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Connection Limits (Sprint 2)
# ---------------------------------------------------------------------------


class ConnectionLimitsResponse(BaseModel):
    """Current accel-ppp connection limit settings.

    Attributes:
        max_sessions: Maximum concurrent sessions allowed (0 = unlimited).
        max_starting: Maximum sessions in the starting/negotiation phase.
        session_timeout: Absolute session timeout in seconds (0 = disabled).
    """

    max_sessions: int = 0
    max_starting: int = 0
    session_timeout: int = 0


class SetLimitsRequest(BaseModel):
    """Request to update accel-ppp connection limits.

    Only provided fields are changed; omitted fields remain unmodified.

    Attributes:
        max_sessions: Maximum concurrent sessions (0 = unlimited).
        max_starting: Maximum sessions in starting state.
    """

    max_sessions: int | None = Field(None, ge=0, description="Max concurrent sessions")
    max_starting: int | None = Field(
        None, ge=0, description="Max sessions in starting state"
    )


class InterfaceLimitResponse(BaseModel):
    """PADI rate-limit setting for a specific PPPoE interface.

    Attributes:
        interface: Interface name queried.
        padi_limit: Maximum PADI packets per second (0 = unlimited).
        found: Whether the interface was found in the configuration.
    """

    interface: str = ""
    padi_limit: int = 0
    found: bool = False


# ---------------------------------------------------------------------------
# PADO Delay (Sprint 2)
# ---------------------------------------------------------------------------


class PadoDelayResponse(BaseModel):
    """Current PADO (PPPoE Active Discovery Offer) delay settings.

    PADO delay throttles how quickly the BNG responds to discovery
    requests, which can protect against burst storms.

    Attributes:
        delay: Current PADO delay in milliseconds.
        min_sessions: Session count threshold before the delay kicks in.
        description: Human-readable explanation of the current setting.
    """

    delay: int = 0
    min_sessions: int = 0
    description: str = ""


class SetPadoDelayRequest(BaseModel):
    """Request to change the PADO delay configuration.

    Attributes:
        delay: PADO delay in milliseconds (0 disables).
        min_sessions: Apply the delay only after this many active sessions.
    """

    delay: int = Field(..., ge=0, description="PADO delay in milliseconds")
    min_sessions: int = Field(0, ge=0, description="Apply delay after N sessions")


# ---------------------------------------------------------------------------
# IP Pool (Sprint 2)
# ---------------------------------------------------------------------------


class IpPool(BaseModel):
    """A single IP address pool defined in the accel-ppp configuration.

    Attributes:
        name: Pool label/name.
        range: CIDR range or address range string.
    """

    name: str = ""
    range: str = Field("", alias="range")

    model_config = {"populate_by_name": True}


class IpPoolListResponse(BaseModel):
    """List of configured IP address pools.

    Attributes:
        count: Number of pools.
        pools: List of :class:`IpPool` objects.
    """

    count: int = 0
    pools: list[IpPool] = []


class AddPoolRequest(BaseModel):
    """Request to add a new IP address pool.

    Attributes:
        name: Human-readable pool label.
        ip_range: CIDR notation range (e.g. ``"10.0.0.0/24"``).
    """

    name: str = Field(..., description="Pool name label", pattern=_RE_SAFE_NAME)
    ip_range: str = Field(
        ...,
        description="CIDR range, e.g. 10.0.0.0/24",
        pattern=_RE_SAFE_IP,
    )


class RemovePoolResponse(BaseModel):
    """Result of removing an IP address pool.

    Attributes:
        success: Whether the pool was removed.
        message: Human-readable outcome description.
    """

    success: bool = False
    message: str = ""


class PoolUsageResponse(BaseModel):
    """IP pool utilisation statistics.

    Attributes:
        used: Number of IP addresses currently leased.
        total: Total number of addresses in the pool.
        available: Number of addresses available for allocation.
    """

    used: str = "0"
    total: str = "0"
    available: str = "0"


# ---------------------------------------------------------------------------
# LLDP (Sprint 2)
# ---------------------------------------------------------------------------


class LldpStatusResponse(BaseModel):
    """LLDP (Link Layer Discovery Protocol) daemon status.

    Attributes:
        running: Whether the LLDP daemon is active.
        raw_output: Raw status command output.
    """

    running: bool = False
    raw_output: str = ""


class LldpNeighbor(BaseModel):
    """A single LLDP neighbour discovered on a local interface.

    Attributes:
        local_interface: Local interface where the neighbour was seen.
        chassis_name: Neighbour's system name / chassis ID.
        port_id: Neighbour's port identifier.
        port_description: Neighbour's port description TLV.
        ttl: Time-to-live of the LLDP advertisement.
    """

    local_interface: str = ""
    chassis_name: str = ""
    port_id: str = ""
    port_description: str = ""
    ttl: str = ""


class LldpNeighborsResponse(BaseModel):
    """List of all discovered LLDP neighbours.

    Attributes:
        count: Number of neighbours discovered.
        neighbors: List of :class:`LldpNeighbor` objects.
        raw_output: Raw command output for debugging.
    """

    count: int = 0
    neighbors: list[LldpNeighbor] = []
    raw_output: str = ""


class LldpInterfaceResponse(BaseModel):
    """LLDP neighbours for a specific interface.

    Attributes:
        interface: The queried interface name.
        found: Whether any neighbours were discovered on this interface.
        neighbors: List of :class:`LldpNeighbor` objects.
        raw_output: Raw command output for debugging.
    """

    interface: str = ""
    found: bool = False
    neighbors: list[LldpNeighbor] = []
    raw_output: str = ""


# ---------------------------------------------------------------------------
# DHCP (Sprint 3)
# ---------------------------------------------------------------------------


class DhcpStatusResponse(BaseModel):
    """DHCP server/relay daemon status.

    Attributes:
        active: Whether the DHCP service is running.
        service: Systemd service unit name.
        lease_count: Number of active DHCP leases.
        raw_output: Raw command output for debugging.
    """

    active: bool = False
    service: str = ""
    lease_count: int = 0
    raw_output: str = ""


class DhcpLease(BaseModel):
    """A single active DHCP lease entry.

    Attributes:
        expires: Lease expiry as a Unix epoch timestamp.
        mac: Client's hardware (MAC) address.
        ip: IP address leased to the client.
        hostname: Client-reported hostname, if any.
        client_id: DHCP client identifier.
    """

    expires: int = 0
    mac: str = ""
    ip: str = ""
    hostname: str = ""
    client_id: str = ""


class DhcpLeasesResponse(BaseModel):
    """List of active DHCP leases.

    Attributes:
        count: Number of active leases.
        leases: List of :class:`DhcpLease` objects.
        raw_output: Raw lease file content for debugging.
    """

    count: int = 0
    leases: list[DhcpLease] = []
    raw_output: str = ""


class DhcpRelayStatusResponse(BaseModel):
    """DHCP relay agent status and configuration.

    Attributes:
        active: Whether the relay service is running.
        service: Systemd service unit name.
        config: Parsed relay configuration key-value pairs.
        raw_output: Raw command output for debugging.
    """

    active: bool = False
    service: str = ""
    config: dict = {}
    raw_output: str = ""


class DhcpActionResponse(BaseModel):
    """Result of a DHCP service action (start/stop/restart).

    Attributes:
        success: Whether the action completed without error.
        message: Human-readable outcome description.
    """

    success: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Flow Accounting (Sprint 3)
# ---------------------------------------------------------------------------


class FlowStatusResponse(BaseModel):
    """NetFlow/sFlow/IPFIX flow-accounting daemon status.

    Attributes:
        active: Whether the flow-accounting daemon is running.
        daemon: Daemon name (e.g. ``"softflowd"``, ``"pmacctd"``).
        raw_output: Raw status command output.
    """

    active: bool = False
    daemon: str = ""
    raw_output: str = ""


class FlowCollector(BaseModel):
    """A configured flow data collector endpoint.

    Attributes:
        host: Collector hostname or IP address.
        port: Collector listening port.
        protocol: Flow protocol (``"netflow5"``, ``"netflow9"``, ``"ipfix"``).
        source: Source IP address used when sending flows.
    """

    host: str = ""
    port: int = 0
    protocol: str = ""
    source: str = ""


class FlowCollectorsResponse(BaseModel):
    """List of configured flow data collectors.

    Attributes:
        count: Number of configured collectors.
        collectors: List of :class:`FlowCollector` objects.
    """

    count: int = 0
    collectors: list[FlowCollector] = []


class FlowStatsResponse(BaseModel):
    """Flow-accounting export statistics.

    Attributes:
        flows_exported: Total flows exported since daemon start.
        packets_processed: Total packets processed by the flow engine.
        raw_output: Raw statistics output.
    """

    flows_exported: int = 0
    packets_processed: int = 0
    raw_output: str = ""


class FlowRestartResponse(BaseModel):
    """Result of restarting the flow-accounting daemon.

    Attributes:
        success: Whether the restart succeeded.
        daemon: Name of the daemon that was restarted.
        message: Human-readable outcome description.
    """

    success: bool = False
    daemon: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Event Handler (Sprint 3)
# ---------------------------------------------------------------------------


class EventHookRequest(BaseModel):
    """Request to register a new event hook (webhook or shell command).

    Attributes:
        name: Unique human-readable identifier for the hook.
        event: Event type to listen for (e.g. ``"session.up"``).
        action: Webhook URL or shell command to execute when fired.
        enabled: Whether the hook should be active immediately.
    """

    name: str = Field(..., description="Unique hook name", pattern=_RE_SAFE_NAME)
    event: str = Field(..., description="Event type", pattern=_RE_SAFE_NAME)
    action: str = Field(..., description="Webhook URL or shell command")
    enabled: bool = True


class EventHookResponse(BaseModel):
    """Details of a registered event hook.

    Attributes:
        name: Hook identifier.
        event: Event type this hook listens for.
        action: Webhook URL or shell command.
        enabled: Whether the hook is active.
        fire_count: Number of times this hook has been triggered.
    """

    name: str = ""
    event: str = ""
    action: str = ""
    enabled: bool = True
    fire_count: int = 0


class EventHookListResponse(BaseModel):
    """List of all registered event hooks.

    Attributes:
        count: Number of hooks registered.
        hooks: List of :class:`EventHookResponse` objects.
    """

    count: int = 0
    hooks: list[EventHookResponse] = []


class FireEventRequest(BaseModel):
    """Request to manually fire a synthetic event.

    Attributes:
        event: Event type string to dispatch.
        payload: Arbitrary JSON payload to include with the event.
    """

    event: str = Field(
        ...,
        description="Event type to fire",
        pattern=_RE_SAFE_NAME,
    )
    payload: dict = {}


class FireEventResponse(BaseModel):
    """Result of manually firing an event.

    Attributes:
        event: Event type that was dispatched.
        hooks_fired: Number of hooks that were triggered.
        results: List of per-hook execution results.
        timestamp: ISO-8601 timestamp of the event dispatch.
    """

    event: str = ""
    hooks_fired: int = 0
    results: list[dict] = []
    timestamp: str = ""


class EventHistoryResponse(BaseModel):
    """Historical log of events that have been fired.

    Attributes:
        count: Number of history entries.
        entries: List of event-history records (raw dictionaries).
    """

    count: int = 0
    entries: list[dict] = []


# ---------------------------------------------------------------------------
# Zone Firewall (Sprint 4)
# ---------------------------------------------------------------------------


class FirewallZone(BaseModel):
    """A named firewall zone grouping interfaces and policies.

    Attributes:
        name: Zone name (e.g. ``"wan"``, ``"lan"``, ``"dmz"``).
        type: Zone type classifier.
        description: Human-readable description of the zone's purpose.
    """

    name: str = ""
    type: str = ""
    description: str = ""


class ZoneListResponse(BaseModel):
    """List of all defined firewall zones.

    Attributes:
        count: Number of zones.
        zones: List of :class:`FirewallZone` objects.
        raw_output: Raw nftables output for debugging.
    """

    count: int = 0
    zones: list[FirewallZone] = []
    raw_output: str = ""


class ZoneDetailRule(BaseModel):
    """A single firewall rule within a zone.

    Attributes:
        chain: nftables chain the rule belongs to.
        rule: Raw rule expression string.
    """

    chain: str = ""
    rule: str = ""


class ZoneDetailResponse(BaseModel):
    """Detailed rules for a specific firewall zone.

    Attributes:
        zone: Zone name that was queried.
        found: Whether the zone exists.
        rules: List of :class:`ZoneDetailRule` objects within the zone.
        raw_output: Raw nftables output for debugging.
    """

    zone: str = ""
    found: bool = False
    rules: list[ZoneDetailRule] = []
    raw_output: str = ""


class CreateZoneRequest(BaseModel):
    """Request to create a new firewall zone.

    Attributes:
        name: Zone name to create.
        interfaces: List of interfaces to assign to the zone.
    """

    name: str = Field(..., description="Zone name", pattern=_RE_SAFE_IFACE)
    interfaces: list[str] = []

    @field_validator("interfaces")
    @classmethod
    def _safe_interfaces(cls, val: list[str]) -> list[str]:
        """Reject shell metacharacters in interface list items."""
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_IFACE)
        for item in val:
            if not pat.match(item):
                msg = f"Invalid interface name: {item!r}"
                raise ValueError(msg)
        return val


class ZoneActionResponse(BaseModel):
    """Result of a firewall zone create/delete/modify operation.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
    """

    success: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Firewall Groups (Sprint 4)
# ---------------------------------------------------------------------------


class FirewallGroup(BaseModel):
    """A named firewall group (address set, network set, or port set).

    Attributes:
        name: Group name.
        type: Group type (``"address"``, ``"network"``, or ``"port"``).
        elements: List of member elements in the group.
    """

    name: str = ""
    type: str = ""
    elements: list[str] = []


class FirewallGroupListResponse(BaseModel):
    """List of all defined firewall groups.

    Attributes:
        count: Number of groups.
        groups: List of :class:`FirewallGroup` objects.
        raw_output: Raw nftables output for debugging.
    """

    count: int = 0
    groups: list[FirewallGroup] = []
    raw_output: str = ""


class CreateGroupRequest(BaseModel):
    """Request to create a new firewall group.

    Attributes:
        name: Group name to create.
        group_type: Type of group — ``"address"``, ``"network"``, or ``"port"``.
        elements: Initial elements to add to the group.
    """

    name: str = Field(..., description="Group name", pattern=_RE_SAFE_IFACE)
    group_type: str = Field(
        ...,
        description="address, network, or port",
        pattern=r"^(address|network|port)$",
    )
    elements: list[str] = []

    @field_validator("elements")
    @classmethod
    def _safe_elements(cls, val: list[str]) -> list[str]:
        """Reject shell metacharacters in initial group elements."""
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_ELEMENT)
        for item in val:
            if not pat.match(item):
                msg = f"Invalid element value: {item!r}"
                raise ValueError(msg)
        return val


class GroupActionResponse(BaseModel):
    """Result of a firewall group create/delete operation.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
        name: Group name that was operated on.
        type: Group type.
    """

    success: bool = False
    message: str = ""
    name: str = ""
    type: str = ""


class AddMembersRequest(BaseModel):
    """Request to add elements to an existing firewall group.

    Attributes:
        elements: One or more elements to add to the group.
    """

    elements: list[str] = Field(..., min_length=1, description="Elements to add")

    @field_validator("elements")
    @classmethod
    def _safe_elements(cls, val: list[str]) -> list[str]:
        """Reject shell metacharacters in group element values."""
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_ELEMENT)
        for item in val:
            if not pat.match(item):
                msg = f"Invalid element value: {item!r}"
                raise ValueError(msg)
        return val


class MemberActionResponse(BaseModel):
    """Result of adding or removing elements from a firewall group.

    Attributes:
        success: Whether the operation completed without error.
        message: Human-readable outcome description.
    """

    success: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# VRRP / HA (Sprint 4)
# ---------------------------------------------------------------------------


class VrrpGroup(BaseModel):
    """A single VRRP (Virtual Router Redundancy Protocol) group.

    Attributes:
        name: VRRP group name / identifier.
        state: Current VRRP state (``"MASTER"``, ``"BACKUP"``, ``"FAULT"``).
        priority: Election priority (higher = more likely to be master).
        vip: Virtual IP address owned by this group.
    """

    name: str = ""
    state: str = ""
    priority: int = 0
    vip: str = ""


class VrrpStatusResponse(BaseModel):
    """VRRP subsystem status and group listing.

    Attributes:
        active: Whether the VRRP daemon (keepalived) is running.
        service: Systemd service unit name.
        groups: List of :class:`VrrpGroup` objects.
        raw_output: Raw command output for debugging.
    """

    active: bool = False
    service: str = ""
    groups: list[VrrpGroup] = []
    raw_output: str = ""


class VrrpGroupDetailResponse(BaseModel):
    """Detailed information for a single VRRP group.

    Attributes:
        found: Whether the group exists.
        group: The :class:`VrrpGroup` object, or ``None`` if not found.
    """

    found: bool = False
    group: VrrpGroup | None = None


class VrrpFailoverRequest(BaseModel):
    """Request to trigger a manual VRRP failover.

    Attributes:
        group: VRRP group name to fail over.
    """

    group: str = Field(
        ...,
        description="VRRP group name",
        pattern=_RE_SAFE_NAME,
    )


class VrrpActionResponse(BaseModel):
    """Result of a VRRP failover or priority-change operation.

    Attributes:
        success: Whether the action completed without error.
        group: VRRP group that was targeted.
        message: Human-readable outcome description.
    """

    success: bool = False
    group: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Monitoring Export (Sprint 4)
# ---------------------------------------------------------------------------


class MonitoringExporter(BaseModel):
    """A Prometheus / metrics exporter service.

    Attributes:
        service: Exporter systemd service name.
        active: Whether the exporter is running.
        port: HTTP port the exporter listens on for scrapes.
    """

    service: str = ""
    active: bool = False
    port: int = 0


class MonitoringStatusResponse(BaseModel):
    """Status of all monitoring exporter services.

    Attributes:
        exporters: List of :class:`MonitoringExporter` objects.
        count: Number of known exporters.
    """

    exporters: list[MonitoringExporter] = []
    count: int = 0


class MetricEntry(BaseModel):
    """A single Prometheus metric name-value pair.

    Attributes:
        name: Metric name.
        value: Current metric value as a string.
    """

    name: str = ""
    value: str = ""


class ExporterMetricsResponse(BaseModel):
    """Metrics scraped from a specific exporter.

    Attributes:
        service: Exporter service name.
        available: Whether the exporter's metrics endpoint is reachable.
        metrics: List of :class:`MetricEntry` objects.
        raw_output: Raw metrics output for debugging.
    """

    service: str = ""
    available: bool = False
    metrics: list[MetricEntry] = []
    raw_output: str = ""


class ConfigureExporterRequest(BaseModel):
    """Request to enable or disable a monitoring exporter.

    Attributes:
        service: Exporter service name to configure.
        enable: ``True`` to enable, ``False`` to disable.
    """

    service: str = Field(
        ...,
        description="Exporter service name",
        pattern=_RE_SAFE_IFACE,
    )
    enable: bool = True


class ExporterActionResponse(BaseModel):
    """Result of enabling or disabling a monitoring exporter.

    Attributes:
        success: Whether the operation completed without error.
        service: Exporter service name.
        enabled: Resulting enabled state.
        message: Human-readable outcome description.
    """

    success: bool = False
    service: str = ""
    enabled: bool = False
    message: str = ""


class ExporterRestartResponse(BaseModel):
    """Result of restarting a monitoring exporter service.

    Attributes:
        success: Whether the restart completed without error.
        service: Exporter service name.
        message: Human-readable outcome description.
    """

    success: bool = False
    service: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEntry(BaseModel):
    """A single audit log entry from the in-memory ring buffer.

    Attributes:
        timestamp: ISO-8601 UTC timestamp of the request.
        method: HTTP method (POST, PUT, PATCH, DELETE).
        path: Request path (no query string).
        client_ip: Remote client IP address.
        request_id: Trace ID assigned by the request-ID middleware.
        role: RBAC role of the caller or ``-`` if unavailable.
        status: HTTP response status code.
        duration_ms: Response time in milliseconds.
    """

    timestamp: str = ""
    method: str = ""
    path: str = ""
    client_ip: str = ""
    request_id: str = ""
    role: str = ""
    status: int = 0
    duration_ms: float = 0.0


class AuditListResponse(BaseModel):
    """Response for the audit log listing endpoint.

    Attributes:
        count: Number of entries returned.
        buffer_size: Maximum capacity of the ring buffer.
        entries: Audit log entries, newest first.
    """

    count: int = 0
    buffer_size: int = 0
    entries: list[AuditEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------


class PlaybookInfo(BaseModel):
    """Metadata for a single available playbook.

    Attributes:
        name: Machine-friendly playbook identifier.
        description: Human-readable summary of what the playbook does.
        role_required: Minimum RBAC role needed to run this playbook.
    """

    name: str = ""
    description: str = ""
    role_required: str = ""


class PlaybookListResponse(BaseModel):
    """Response for the playbook listing endpoint.

    Attributes:
        count: Number of available playbooks.
        playbooks: List of playbook metadata.
    """

    count: int = 0
    playbooks: list[PlaybookInfo] = Field(default_factory=list)


class PlaybookStep(BaseModel):
    """Result of a single step within a playbook execution.

    Attributes:
        step: Human-readable step name.
        success: Whether the step completed without error.
        detail: Outcome description or error message.
    """

    step: str = ""
    success: bool = False
    detail: str = ""


class PlaybookRunResponse(BaseModel):
    """Response for a playbook execution request.

    Attributes:
        playbook: Name of the playbook that was executed.
        success: True if all steps completed successfully.
        steps: Ordered list of step results.
    """

    playbook: str = ""
    success: bool = False
    steps: list[PlaybookStep] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

#: Hard ceiling for items in a single bulk request to prevent abuse.
BULK_MAX_ITEMS = 100


class BulkTerminateRequest(BaseModel):
    """Request to terminate multiple subscriber sessions in one call.

    Attributes:
        usernames: List of subscriber usernames to disconnect.
    """

    usernames: list[str] = Field(
        min_length=1,
        max_length=BULK_MAX_ITEMS,
        description="Usernames to terminate (1-100)",
    )

    @field_validator("usernames")
    @classmethod
    def _validate_names(cls, v: list[str]) -> list[str]:
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_NAME)
        for name in v:
            if not pat.match(name):
                raise ValueError(f"Invalid username: {name}")
        return v


class BulkRateLimitItem(BaseModel):
    """A single username-rate pair for bulk rate-limit changes.

    Attributes:
        username: Subscriber whose shaper should be changed.
        rate: Bandwidth string in upload/download format.
    """

    username: str = Field(pattern=_RE_SAFE_NAME)
    rate: str = Field(pattern=_RE_SAFE_RATE)


class BulkRateLimitRequest(BaseModel):
    """Request to change rate limits for multiple subscribers.

    Attributes:
        items: List of username-rate pairs to apply.
    """

    items: list[BulkRateLimitItem] = Field(
        min_length=1,
        max_length=BULK_MAX_ITEMS,
        description="Rate-limit changes to apply (1-100)",
    )


class BulkShaperRestoreRequest(BaseModel):
    """Request to restore original RADIUS-assigned shapers.

    Attributes:
        usernames: List of subscriber usernames to restore.
    """

    usernames: list[str] = Field(
        min_length=1,
        max_length=BULK_MAX_ITEMS,
        description="Usernames to restore (1-100)",
    )

    @field_validator("usernames")
    @classmethod
    def _validate_names(cls, v: list[str]) -> list[str]:
        import re  # pylint: disable=import-outside-toplevel

        pat = re.compile(_RE_SAFE_NAME)
        for name in v:
            if not pat.match(name):
                raise ValueError(f"Invalid username: {name}")
        return v


class BulkResultItem(BaseModel):
    """Outcome of a single item within a bulk operation.

    Attributes:
        target: Identifier of the item (e.g. username).
        success: Whether this individual operation succeeded.
        message: Human-readable outcome or error detail.
    """

    target: str = ""
    success: bool = False
    message: str = ""


class BulkOperationResponse(BaseModel):
    """Aggregated result of a bulk operation.

    Attributes:
        operation: Name of the bulk operation performed.
        total: Total number of items submitted.
        succeeded: Count of items that completed successfully.
        failed: Count of items that failed.
        results: Per-item outcome details.
    """

    operation: str = ""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[BulkResultItem] = Field(default_factory=list)
