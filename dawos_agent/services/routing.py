"""FRR (Free Range Routing) management — BGP, OSPF, and RIP via vtysh.

Wraps ``sudo vtysh -c '<command>'`` for reading FRR state.  Mutating
operations (neighbor add/remove) are intentionally **not** exposed — those
should go through FRR config files or ``vtysh configure terminal`` sessions
managed by an operator.
"""

from __future__ import annotations

import asyncio
import logging
import re

log = logging.getLogger(__name__)


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
        log.warning(
            "command failed (rc=%d): %s — %s",
            proc.returncode,
            cmd,
            err,
        )
    return out, proc.returncode


async def _vtysh(command: str) -> str:
    """Run a vtysh command and return its stdout.

    Args:
        command: The FRR vtysh command to execute.

    Returns:
        The stripped stdout text.

    Raises:
        RuntimeError: If vtysh exits with a non-zero return code.
    """
    out, rc = await _run(f"vtysh -c '{command}'", sudo=True)
    if rc != 0:
        raise RuntimeError(f"vtysh failed: {out}")
    return out


# ---------------------------------------------------------------------------
# BGP
# ---------------------------------------------------------------------------


async def bgp_summary() -> dict:
    """Return a parsed BGP summary from FRR.

    Includes the router ID, local AS number, and a list of BGP neighbors
    with their state and prefix counts.

    Returns:
        A dictionary with ``configured`` (bool), ``router_id``,
        ``local_as``, ``neighbors`` (list), ``total_prefixes``,
        and ``raw_output``.
    """
    try:
        raw = await _vtysh("show bgp summary")
    except RuntimeError:
        return {"configured": False, "raw_output": ""}

    result: dict = {
        "configured": True,
        "router_id": "",
        "local_as": "",
        "neighbors": [],
        "total_prefixes": 0,
        "raw_output": raw,
    }

    for line in raw.splitlines():
        # "BGP router identifier 10.0.0.1, local AS number 65000 ..."
        m = re.search(
            r"router identifier ([\d.]+).*local AS number (\d+)",
            line,
        )
        if m:
            result["router_id"] = m.group(1)
            result["local_as"] = m.group(2)
            continue

        # Neighbor lines: "10.0.0.2  4  65001  ...  5"
        parts = line.split()
        if len(parts) >= 5 and _is_ip(parts[0]):
            result["neighbors"].append(
                {
                    "neighbor": parts[0],
                    "remote_as": parts[2] if len(parts) > 2 else "",
                    "state": parts[-2] if len(parts) > 5 else "",
                    "up_down": parts[-3] if len(parts) > 5 else "",
                    "prefixes_received": _safe_int(parts[-1]),
                }
            )
            result["total_prefixes"] += _safe_int(parts[-1])

    return result


async def bgp_routes() -> dict:
    """Return the BGP IPv4 unicast routing table.

    Returns:
        A dictionary with ``count`` (number of lines) and ``raw_output``.
    """
    try:
        raw = await _vtysh("show bgp ipv4 unicast")
    except RuntimeError:
        return {"count": 0, "raw_output": ""}

    count = raw.count("\n")
    return {"count": count, "raw_output": raw}


# ---------------------------------------------------------------------------
# OSPF
# ---------------------------------------------------------------------------


async def ospf_status() -> dict:
    """Return parsed OSPF status from FRR.

    Returns:
        A dictionary with ``configured`` (bool), ``router_id``,
        ``neighbors`` (list), and ``raw_output``.
    """
    try:
        raw = await _vtysh("show ip ospf")
    except RuntimeError:
        return {"configured": False, "raw_output": ""}

    result: dict = {
        "configured": True,
        "router_id": "",
        "neighbors": [],
        "raw_output": raw,
    }

    m = re.search(r"OSPF Routing Process.*Router ID[:\s]+([\d.]+)", raw)
    if m:
        result["router_id"] = m.group(1)

    return result


async def ospf_neighbors() -> dict:
    """Return the OSPF neighbor table from FRR.

    Returns:
        A dictionary with ``configured`` (bool), ``neighbors`` (list of
        dicts with ``neighbor_id``, ``priority``, ``state``, ``address``,
        ``interface``), and ``raw_output``.
    """
    try:
        raw = await _vtysh("show ip ospf neighbor")
    except RuntimeError:
        return {"configured": False, "neighbors": [], "raw_output": ""}

    neighbors = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 5 and _is_ip(parts[0]):
            neighbors.append(
                {
                    "neighbor_id": parts[0],
                    "priority": _safe_int(parts[1]),
                    "state": parts[2] if len(parts) > 2 else "",
                    "address": parts[3] if len(parts) > 3 else "",
                    "interface": parts[4] if len(parts) > 4 else "",
                }
            )

    return {
        "configured": True,
        "neighbors": neighbors,
        "raw_output": raw,
    }


async def ospf_routes() -> dict:
    """Return the OSPF routing table from FRR.

    Returns:
        A dictionary with ``count`` (number of lines) and ``raw_output``.
    """
    try:
        raw = await _vtysh("show ip ospf route")
    except RuntimeError:
        return {"count": 0, "raw_output": ""}

    count = raw.count("\n")
    return {"count": count, "raw_output": raw}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_ip(text: str) -> bool:
    """Check whether a string looks like a valid IPv4 address.

    Args:
        text: The string to test.

    Returns:
        True if *text* matches the IPv4 dotted-decimal pattern.
    """
    parts = text.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _safe_int(value, default: int = 0) -> int:
    """Convert a value to an integer, returning *default* on failure.

    Args:
        value: The value to convert.
        default: Fallback value if conversion fails.

    Returns:
        The parsed integer or *default*.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# RIP
# ---------------------------------------------------------------------------


async def rip_status() -> dict:
    """Return parsed RIP status from FRR.

    Includes the protocol version, advertised networks, and neighbor list.

    Returns:
        A dictionary with ``configured`` (bool), ``version``,
        ``networks`` (list), ``neighbors`` (list), and ``raw_output``.
    """
    try:
        raw = await _vtysh("show ip rip status")
    except RuntimeError:
        return {"configured": False, "raw_output": ""}

    result: dict = {
        "configured": True,
        "version": "",
        "networks": [],
        "neighbors": [],
        "raw_output": raw,
    }

    in_network = False
    in_neighbor = False
    for line in raw.splitlines():
        # "Routing Protocol is \"rip\""
        if "Routing Protocol" in line and "rip" in line.lower():
            m = re.search(r"version\s+(\d+)", line, re.IGNORECASE)
            if m:
                result["version"] = m.group(1)

        # "Sending updates every 30 seconds" — version line variant
        m = re.search(r"Default version control:\s+send version\s+(\d+)", line)
        if m:
            result["version"] = m.group(1)

        if "Network" in line and "next" not in line.lower():
            in_network = True
            in_neighbor = False
            continue
        if "Neighbor" in line:
            in_neighbor = True
            in_network = False
            continue
        if line.strip() == "":
            in_network = False
            in_neighbor = False
            continue

        stripped = line.strip()
        if in_network and stripped:
            result["networks"].append(stripped)
        if in_neighbor and stripped and _is_ip(stripped.split()[0]):
            result["neighbors"].append(stripped.split()[0])

    return result


async def rip_routes() -> dict:
    """Return the RIP routing table entries from FRR.

    Returns:
        A dictionary with ``count``, ``routes`` (list of dicts with
        ``code``, ``network``, ``nexthop``, ``metric``), and
        ``raw_output``.
    """
    try:
        raw = await _vtysh("show ip rip")
    except RuntimeError:
        return {"count": 0, "routes": [], "raw_output": ""}

    routes: list[dict] = []
    for line in raw.splitlines():
        # RIP table lines: "R(n) 10.0.0.0/24  via 10.0.0.1  2  eth0  00:25"
        parts = line.split()
        if len(parts) < 4:
            continue
        code = parts[0]
        if not (code.startswith("R") or code == "C"):
            continue
        # Skip header lines like "Codes: R - RIP, C - connected, ..."
        if code.endswith(":"):
            continue
        network = parts[1] if len(parts) > 1 else ""
        # Find "via" keyword for next-hop
        nexthop = ""
        metric = 0
        if "via" in parts:
            via_idx = parts.index("via")
            nexthop = parts[via_idx + 1] if via_idx + 1 < len(parts) else ""
        # Metric is usually after nexthop
        for p in parts[2:]:
            if p.isdigit():
                metric = int(p)
                break
        routes.append(
            {
                "code": code,
                "network": network,
                "nexthop": nexthop,
                "metric": metric,
            }
        )

    return {"count": len(routes), "routes": routes, "raw_output": raw}


# ---------------------------------------------------------------------------
# BFD (Bidirectional Forwarding Detection)
# ---------------------------------------------------------------------------


async def bfd_peers() -> dict:
    """Return BFD peer status via ``show bfd peers``.

    Returns:
        A dictionary with ``configured`` (bool), ``peers`` (list of
        dicts with ``peer``, ``interface``, ``status``, ``uptime``),
        ``count``, and ``raw_output``.
    """
    try:
        raw = await _vtysh("show bfd peers")
    except RuntimeError:
        return {"configured": False, "peers": [], "raw_output": ""}

    peers: list[dict] = []
    current: dict = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("peer "):
            if current:
                peers.append(current)
            parts = stripped.split()
            current = {
                "peer": parts[1] if len(parts) > 1 else "",
                "interface": "",
                "status": "",
                "uptime": "",
            }
        elif "interface:" in stripped.lower():
            current["interface"] = stripped.split(":", 1)[1].strip()
        elif "status:" in stripped.lower():
            current["status"] = stripped.split(":", 1)[1].strip()
        elif "uptime:" in stripped.lower():
            current["uptime"] = stripped.split(":", 1)[1].strip()
    if current:
        peers.append(current)

    return {
        "configured": True,
        "peers": peers,
        "count": len(peers),
        "raw_output": raw,
    }


async def bfd_summary() -> dict:
    """Return BFD counters summary.

    Returns:
        A dictionary with ``configured`` (bool) and ``raw_output``.
    """
    try:
        raw = await _vtysh("show bfd peers counters")
    except RuntimeError:
        return {"configured": False, "raw_output": ""}

    return {"configured": bool(raw.strip()), "raw_output": raw}
