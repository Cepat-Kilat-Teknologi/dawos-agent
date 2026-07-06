"""IP pool management for accel-ppp.

Manages the ``[ip-pool]`` section in the accel-ppp configuration file.
Provides CRUD operations for named IP pools and real-time utilisation
data via ``accel-cmd show ippool``.
"""

from __future__ import annotations

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
