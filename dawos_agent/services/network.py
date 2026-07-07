"""Network management — interfaces, VLANs, routes, DNS.

Wraps Linux ``ip`` commands with JSON output (``ip -j``) for reliable
parsing.  All mutating operations use ``sudo`` and are designed to run
on a Debian/Ubuntu BNG node where the dawos service user has limited
sudoers for networking commands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from ..models.schemas import (
    DnsConfig,
    InterfaceAddress,
    InterfaceDetail,
    RouteEntry,
    VlanInfo,
)

log = logging.getLogger(__name__)

RESOLV_CONF = Path("/etc/resolv.conf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(cmd: str, *, sudo: bool = False) -> tuple[str, int]:
    """Execute a shell command asynchronously.

    Args:
        cmd: The command string to execute.
        sudo: If True, prefix the command with ``sudo``.

    Returns:
        A tuple of (stdout_text, return_code).
    """
    if sudo:
        cmd = f"sudo {cmd}"
    log.debug("exec: %s", cmd)
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("command failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def _run_ok(cmd: str, *, sudo: bool = False) -> str:
    """Execute a shell command, raising on failure.

    Args:
        cmd: The command string to execute.
        sudo: If True, prefix the command with ``sudo``.

    Returns:
        The stripped stdout text.

    Raises:
        RuntimeError: If the command exits with a non-zero return code.
    """
    out, rc = await _run(cmd, sudo=sudo)
    if rc != 0:
        raise RuntimeError(f"Command failed: {cmd} — {out}")
    return out


def _parse_ip_json(text: str) -> list[dict[str, Any]]:
    """Parse ``ip -j`` JSON output into a list of dictionaries.

    Args:
        text: Raw JSON string from an ``ip -j`` command.

    Returns:
        A list of parsed dictionaries, or an empty list on parse failure.
    """
    if not text:
        return []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        log.warning("Failed to parse ip JSON output")
        return []


# ---------------------------------------------------------------------------
# Interface management
# ---------------------------------------------------------------------------


async def list_interfaces(*, include_loopback: bool = False) -> list[InterfaceDetail]:
    """List all network interfaces with their assigned addresses.

    Uses ``ip -j addr show`` for structured JSON output.

    Args:
        include_loopback: If True, include the loopback interface.

    Returns:
        A list of :class:`InterfaceDetail` objects.

    Raises:
        RuntimeError: If the ``ip`` command fails.
    """
    out, rc = await _run("ip -j addr show")
    if rc != 0:
        raise RuntimeError(f"Failed to list interfaces: {out}")

    data = _parse_ip_json(out)
    interfaces: list[InterfaceDetail] = []

    for iface in data:
        name = iface.get("ifname", "")
        if not include_loopback and name == "lo":
            continue

        addresses: list[InterfaceAddress] = []
        for addr in iface.get("addr_info", []):
            addresses.append(
                InterfaceAddress(
                    family=addr.get("family", ""),
                    address=addr.get("local", ""),
                    prefix_len=addr.get("prefixlen", 0),
                    broadcast=addr.get("broadcast"),
                    scope=addr.get("scope", ""),
                )
            )

        interfaces.append(
            InterfaceDetail(
                name=name,
                index=iface.get("ifindex", 0),
                mac_address=iface.get("address", ""),
                mtu=iface.get("mtu", 1500),
                state=iface.get("operstate", "UNKNOWN"),
                flags=iface.get("flags", []),
                addresses=addresses,
                link_type=iface.get("link_type", ""),
            )
        )

    return interfaces


async def get_interface(name: str) -> InterfaceDetail:
    """Get detailed information for a specific network interface.

    Args:
        name: The interface name (e.g. ``eth0``).

    Returns:
        An :class:`InterfaceDetail` object.

    Raises:
        RuntimeError: If the interface is not found or has no data.
    """
    out, rc = await _run(f"ip -j addr show dev {name}")
    if rc != 0:
        raise RuntimeError(f"Interface not found: {name}")

    data = _parse_ip_json(out)
    if not data:
        raise RuntimeError(f"No data for interface: {name}")

    iface = data[0]
    addresses: list[InterfaceAddress] = []
    for addr in iface.get("addr_info", []):
        addresses.append(
            InterfaceAddress(
                family=addr.get("family", ""),
                address=addr.get("local", ""),
                prefix_len=addr.get("prefixlen", 0),
                broadcast=addr.get("broadcast"),
                scope=addr.get("scope", ""),
            )
        )

    return InterfaceDetail(
        name=iface.get("ifname", name),
        index=iface.get("ifindex", 0),
        mac_address=iface.get("address", ""),
        mtu=iface.get("mtu", 1500),
        state=iface.get("operstate", "UNKNOWN"),
        flags=iface.get("flags", []),
        addresses=addresses,
        link_type=iface.get("link_type", ""),
    )


async def configure_interface(
    name: str,
    *,
    address: str | None = None,
    remove_address: str | None = None,
    mtu: int | None = None,
    state: str | None = None,
) -> str:
    """Configure a network interface.

    Supports adding/removing IP addresses, setting MTU, and toggling
    the link state in a single call.

    Args:
        name: The interface name (e.g. ``eth0``).
        address: IP in CIDR notation to add (e.g. ``10.0.0.1/24``).
        remove_address: IP in CIDR notation to remove.
        mtu: MTU value to set.
        state: ``"up"`` or ``"down"`` to set the link state.

    Returns:
        A human-readable summary of the changes applied.

    Raises:
        RuntimeError: If any underlying ``ip`` command fails.
    """
    actions: list[str] = []

    if address:
        await _run_ok(f"ip addr add {address} dev {name}", sudo=True)
        actions.append(f"added {address}")

    if remove_address:
        await _run_ok(f"ip addr del {remove_address} dev {name}", sudo=True)
        actions.append(f"removed {remove_address}")

    if mtu is not None:
        await _run_ok(f"ip link set {name} mtu {mtu}", sudo=True)
        actions.append(f"mtu={mtu}")

    if state in ("up", "down"):
        await _run_ok(f"ip link set {name} {state}", sudo=True)
        actions.append(f"state={state}")

    if not actions:
        return "No changes requested"

    return f"Interface {name}: {', '.join(actions)}"


# ---------------------------------------------------------------------------
# VLAN management
# ---------------------------------------------------------------------------


async def create_vlan(parent: str, vlan_id: int, address: str | None = None) -> str:
    """Create a VLAN sub-interface and bring it up.

    Creates ``<parent>.<vlan_id>`` (e.g. ``eth0.100``) and optionally
    assigns an IP address.

    Args:
        parent: Parent interface name (e.g. ``eth0``).
        vlan_id: 802.1Q VLAN identifier.
        address: Optional IP in CIDR notation to assign.

    Returns:
        The created VLAN interface name.

    Raises:
        RuntimeError: If the ``ip`` command fails.
    """
    vlan_name = f"{parent}.{vlan_id}"
    await _run_ok(
        f"ip link add link {parent} name {vlan_name} type vlan id {vlan_id}",
        sudo=True,
    )
    await _run_ok(f"ip link set {vlan_name} up", sudo=True)

    if address:
        await _run_ok(f"ip addr add {address} dev {vlan_name}", sudo=True)

    return vlan_name


async def delete_vlan(name: str) -> str:
    """Delete a VLAN sub-interface.

    Args:
        name: The VLAN interface name to remove (e.g. ``eth0.100``).

    Returns:
        A confirmation message string.

    Raises:
        RuntimeError: If the ``ip`` command fails.
    """
    await _run_ok(f"ip link delete {name}", sudo=True)
    return f"Deleted {name}"


async def list_vlans() -> list[VlanInfo]:
    """List all VLAN sub-interfaces on the system.

    Uses ``ip -j -d link show type vlan`` which returns detailed VLAN
    metadata including parent interface, VLAN ID, and protocol directly
    from the kernel.

    Returns:
        A list of :class:`VlanInfo` objects.

    Raises:
        RuntimeError: If the ``ip`` command fails.
    """
    out, rc = await _run("ip -j -d link show type vlan")
    if rc != 0:
        raise RuntimeError(f"Failed to list VLANs: {out}")

    data = _parse_ip_json(out)
    vlans: list[VlanInfo] = []

    for iface in data:
        linkinfo = iface.get("linkinfo", {})
        info_data = linkinfo.get("info_data", {})

        # Build address list from addr_info if present
        addresses: list[InterfaceAddress] = []
        for addr in iface.get("addr_info", []):
            addresses.append(
                InterfaceAddress(
                    family=addr.get("family", ""),
                    address=addr.get("local", ""),
                    prefix_len=addr.get("prefixlen", 0),
                    broadcast=addr.get("broadcast"),
                    scope=addr.get("scope", ""),
                )
            )

        vlans.append(
            VlanInfo(
                name=iface.get("ifname", ""),
                parent=iface.get("link", ""),
                vlan_id=info_data.get("id", 0),
                protocol=info_data.get("protocol", "802.1Q"),
                state=iface.get("operstate", "UNKNOWN"),
                mac_address=iface.get("address", ""),
                mtu=iface.get("mtu", 1500),
                addresses=addresses,
            )
        )

    return vlans


async def set_vlan_state(name: str, state: str) -> str:
    """Enable or disable a VLAN interface.

    Args:
        name: VLAN interface name (e.g. ``eth0.100``).
        state: ``"up"`` or ``"down"``.

    Returns:
        Human-readable status message.
    """
    if state not in ("up", "down"):
        raise ValueError(f"Invalid state '{state}', must be 'up' or 'down'")

    await _run_ok(f"ip link set {name} {state}", sudo=True)
    return f"VLAN {name} set to {state}"


# ---------------------------------------------------------------------------
# Route management
# ---------------------------------------------------------------------------


async def list_routes() -> list[RouteEntry]:
    """List the IPv4 routing table.

    Uses ``ip -j route show`` for structured JSON output.

    Returns:
        A list of :class:`RouteEntry` objects.

    Raises:
        RuntimeError: If the ``ip`` command fails.
    """
    out, rc = await _run("ip -j route show")
    if rc != 0:
        raise RuntimeError(f"Failed to list routes: {out}")

    data = _parse_ip_json(out)
    routes: list[RouteEntry] = []

    for r in data:
        routes.append(
            RouteEntry(
                destination=r.get("dst", ""),
                gateway=r.get("gateway"),
                device=r.get("dev", ""),
                protocol=r.get("protocol", ""),
                scope=r.get("scope", ""),
                metric=r.get("metric"),
                source=r.get("prefsrc"),
            )
        )

    return routes


async def add_route(
    destination: str,
    gateway: str,
    device: str | None = None,
    metric: int | None = None,
) -> str:
    """Add a static route to the routing table.

    Args:
        destination: Destination network in CIDR notation.
        gateway: Next-hop gateway IP address.
        device: Optional outgoing interface name.
        metric: Optional route metric/priority.

    Returns:
        A confirmation message string.

    Raises:
        RuntimeError: If the ``ip route add`` command fails.
    """
    cmd = f"ip route add {destination} via {gateway}"
    if device:
        cmd += f" dev {device}"
    if metric is not None:
        cmd += f" metric {metric}"

    await _run_ok(cmd, sudo=True)
    return f"Route added: {destination} via {gateway}"


async def delete_route(destination: str, gateway: str | None = None) -> str:
    """Delete a route from the routing table.

    Args:
        destination: Destination network in CIDR notation.
        gateway: Optional gateway to narrow the match.

    Returns:
        A confirmation message string.

    Raises:
        RuntimeError: If the ``ip route del`` command fails.
    """
    cmd = f"ip route del {destination}"
    if gateway:
        cmd += f" via {gateway}"

    await _run_ok(cmd, sudo=True)
    return f"Route deleted: {destination}"


# ---------------------------------------------------------------------------
# DNS management
# ---------------------------------------------------------------------------


def get_dns(resolv_path: Path | None = None) -> DnsConfig:
    """Parse ``/etc/resolv.conf`` and return the DNS configuration.

    Args:
        resolv_path: Override the resolv.conf path (for testing).

    Returns:
        A :class:`DnsConfig` with ``nameservers`` and ``search_domains``.
    """
    path = resolv_path or RESOLV_CONF
    nameservers: list[str] = []
    search_domains: list[str] = []

    if not path.exists():
        return DnsConfig(nameservers=[], search_domains=[])

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("nameserver "):
            ns = line.split(None, 1)[1].strip()
            if ns:
                nameservers.append(ns)
        elif line.startswith("search "):
            domains = line.split()[1:]
            search_domains.extend(domains)

    return DnsConfig(nameservers=nameservers, search_domains=search_domains)


def set_dns(
    nameservers: list[str],
    search_domains: list[str] | None = None,
    resolv_path: Path | None = None,
) -> None:
    """Write ``/etc/resolv.conf`` with the given nameservers.

    Uses ``sudo tee`` to write the file, since ``/etc/resolv.conf`` is
    typically owned by root (or is a symlink to a systemd-resolved
    managed file).

    Args:
        nameservers: List of DNS server IP addresses.
        search_domains: Optional list of DNS search domains.
        resolv_path: Override the resolv.conf path (for testing).
    """
    path = resolv_path or RESOLV_CONF
    lines = ["# Generated by dawos-agent\n"]

    if search_domains:
        lines.append(f"search {' '.join(search_domains)}\n")

    for ns in nameservers:
        lines.append(f"nameserver {ns}\n")

    content = "".join(lines)

    if resolv_path:
        # Testing path — write directly without sudo
        path.write_text(content, encoding="utf-8")
    else:
        # Production — use sudo tee for root-owned files
        result = subprocess.run(  # pylint: disable=subprocess-run-check
            ["sudo", "tee", str(path)],
            input=content.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            err = result.stderr.decode().strip()
            raise PermissionError(
                f"Failed to write {path}: {err}"
            )
