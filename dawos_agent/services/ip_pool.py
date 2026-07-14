"""IP pool management for accel-ppp.

Manages the ``[ip-pool]`` section in the accel-ppp configuration file.
Provides CRUD operations for named IP pools and real-time utilisation
data via ``accel-cmd show ippool``.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from pathlib import Path

from ..config import ACCEL_CONFIG
from . import accel, config_manager

log = logging.getLogger(__name__)


def list_pools(config_path: Path | None = None) -> list[dict]:
    """Parse all pool definitions from the ``[ip-pool]`` section.

    Args:
        config_path: Override the default configuration file path.

    Returns:
        A list of dicts with ``name`` and ``range`` for each pool.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    pools: list[dict] = []
    in_pool = False

    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_pool = line.lower() == "[ip-pool]"
            continue

        if not in_pool:
            continue

        # gw= line
        if line.startswith("gw="):
            continue

        # Named pool:  10.0.0.0/24,pool-name
        # Unnamed pool: 10.0.0.0/24
        m = re.match(r"^(\d+\.\d+\.\d+\.\d+/\d+)(?:,(.+))?$", line)
        if m:
            pool_range = m.group(1)
            pool_name = m.group(2).strip() if m.group(2) else pool_range
            pools.append({"name": pool_name, "range": pool_range})

    return pools


def add_pool(
    name: str,
    ip_range: str,
    config_path: Path | None = None,
) -> str:
    """Add a new IP pool to the ``[ip-pool]`` section.

    Creates a backup before writing.

    Args:
        name: Pool name label.
        ip_range: CIDR range (e.g. ``10.0.0.0/24``).
        config_path: Override the default configuration file path.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If *ip_range* is not valid CIDR or *name* already exists.
        FileNotFoundError: If the configuration file does not exist.
    """
    if not re.match(r"^\d+\.\d+\.\d+\.\d+/\d+$", ip_range):
        raise ValueError(f"Invalid CIDR range: {ip_range}")

    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    current = list_pools(config_path=path)

    # Check for duplicate name
    if any(p["name"] == name for p in current):
        raise ValueError(f"Pool '{name}' already exists")

    # Insert new pool line at end of [ip-pool] section
    lines = content.splitlines()
    out: list[str] = []
    in_pool = False
    inserted = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("["):
            if in_pool and not inserted:
                out.append(f"{ip_range},{name}")
                inserted = True
            in_pool = line.lower() == "[ip-pool]"
            out.append(raw)
            continue
        out.append(raw)

    # [ip-pool] at EOF
    if in_pool and not inserted:
        out.append(f"{ip_range},{name}")

    new_content = "\n".join(out) + "\n"
    config_manager.write_config(new_content, backup=True)
    log.info("Added IP pool %s (%s)", name, ip_range)
    return f"Added pool {name} ({ip_range})"


def remove_pool(name: str, config_path: Path | None = None) -> str:
    """Remove an IP pool by name from the ``[ip-pool]`` section.

    Creates a backup before writing.

    Args:
        name: The pool name to remove.
        config_path: Override the default configuration file path.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If no pool with *name* exists.
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    out: list[str] = []
    in_pool = False
    removed = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("["):
            in_pool = line.lower() == "[ip-pool]"
            out.append(raw)
            continue

        if in_pool:
            # Match: "10.0.0.0/24,pool-name" or bare "10.0.0.0/24"
            m = re.match(r"^(\d+\.\d+\.\d+\.\d+/\d+)(?:,(.+))?$", line)
            if m:
                pool_name = m.group(2).strip() if m.group(2) else m.group(1)
                if pool_name == name:
                    removed = True
                    continue  # skip this line

        out.append(raw)

    if not removed:
        raise ValueError(f"Pool '{name}' not found")

    new_content = "\n".join(out) + "\n"
    config_manager.write_config(new_content, backup=True)
    log.info("Removed IP pool %s", name)
    return f"Removed pool {name}"


async def pool_usage() -> dict:
    """Get real-time IP pool utilisation from accel-cmd.

    Returns:
        A dictionary with ``used``, ``total``, and ``available`` counts.
    """
    info = await accel.show_ippool()
    return {
        "used": info.get("used", "0"),
        "total": info.get("total", "0"),
        "available": info.get("available", "0"),
    }


def _cidr_host_count(cidr: str) -> int:
    """Return the number of usable host addresses in a CIDR range.

    For /31 and /32 networks, returns ``num_addresses`` directly
    (point-to-point or single host).  For larger networks, subtracts
    the network and broadcast addresses.

    Args:
        cidr: CIDR notation string (e.g. ``"10.0.0.0/24"``).

    Returns:
        Number of usable host addresses, or 0 if *cidr* is invalid.
    """
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return 0

    if net.prefixlen >= 31:
        return net.num_addresses
    return max(net.num_addresses - 2, 0)


async def get_pool_detail(  # pylint: disable=too-many-locals
    config_path: Path | None = None,
) -> dict:
    """Get per-pool utilisation with IP-to-user mappings.

    Cross-references configured pools from ``[ip-pool]`` with active
    sessions from ``accel-cmd show sessions`` to produce a detailed
    breakdown of which IPs are in use and by whom within each pool.

    Args:
        config_path: Override the default configuration file path.

    Returns:
        A dictionary suitable for constructing
        :class:`~dawos_agent.models.schemas.IpPoolDetailResponse`.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    pools = list_pools(config_path=config_path)
    sessions = await accel.show_sessions(columns="ip,username")

    # Build network objects for each pool
    pool_nets: list[tuple[dict, ipaddress.IPv4Network | None]] = []
    for pool in pools:
        try:
            net = ipaddress.ip_network(pool["range"], strict=False)
        except ValueError:
            net = None
        pool_nets.append((pool, net))

    # Match each session IP to a pool
    pool_assignments: dict[str, list[dict]] = {p["name"]: [] for p in pools}

    for sess in sessions:
        sess_ip = sess.get("ip", "").strip()
        if not sess_ip:
            continue

        try:
            addr = ipaddress.ip_address(sess_ip)
        except ValueError:
            continue

        for pool, net in pool_nets:
            if net and addr in net:
                pool_assignments[pool["name"]].append(
                    {"ip": sess_ip, "username": sess.get("username", "")}
                )
                break  # IP belongs to at most one pool

    # Build detail entries
    detail_pools: list[dict] = []
    total_used = 0
    total_capacity = 0

    for pool in pools:
        total_ips = _cidr_host_count(pool["range"])
        assignments = pool_assignments[pool["name"]]
        used = len(assignments)
        available = max(total_ips - used, 0)
        pct = round((used / total_ips) * 100, 1) if total_ips > 0 else 0.0

        detail_pools.append(
            {
                "name": pool["name"],
                "range": pool["range"],
                "total_ips": total_ips,
                "used": used,
                "available": available,
                "utilization_pct": pct,
                "assignments": assignments,
            }
        )
        total_used += used
        total_capacity += total_ips

    return {
        "pools": detail_pools,
        "total_pools": len(pools),
        "total_used": total_used,
        "total_capacity": total_capacity,
    }
