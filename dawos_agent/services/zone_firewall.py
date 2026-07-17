"""Zone-based firewall management service.

Wraps ``nft`` for zone-aware firewall policy.  Provides zone CRUD
(backed by nftables inet tables), per-zone rule inspection, and
default chain creation for inter-zone traffic filtering.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex

log = logging.getLogger(__name__)


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
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("zone cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def list_zones() -> dict:
    """List all firewall zones (nftables tables).

    Returns:
        A dictionary with ``count``, ``zones`` (list of dicts with
        ``name``, ``type``, ``description``), and ``raw_output``.
    """
    out, rc = await _run("nft list tables", sudo=True)
    if rc != 0:
        return {"count": 0, "zones": [], "raw_output": out}

    zones: list[dict] = []
    for line in out.splitlines():
        m = re.match(r"table\s+\w+\s+(\S+)", line.strip())
        if m:
            name = m.group(1)
            zones.append(
                {
                    "name": name,
                    "type": "nftables",
                    "description": f"nft table {name}",
                }
            )

    return {"count": len(zones), "zones": zones, "raw_output": out}


async def zone_detail(zone: str) -> dict:
    """Get all rules for a specific firewall zone.

    Args:
        zone: The nftables inet table name representing the zone.

    Returns:
        A dictionary with ``zone``, ``found`` (bool), ``rules``
        (list of dicts with ``chain`` and ``rule``), and ``raw_output``.
    """
    out, rc = await _run(f"nft list table inet {shlex.quote(zone)}", sudo=True)
    if rc != 0:
        return {"zone": zone, "found": False, "rules": [], "raw_output": out}

    rules: list[dict] = []
    chain = ""
    for line in out.splitlines():
        cm = re.match(r"\s*chain\s+(\S+)", line)
        if cm:
            chain = cm.group(1)
            continue
        if "policy" in line or "type" in line:
            continue
        stripped = line.strip()
        if stripped and stripped != "}" and chain:
            rules.append({"chain": chain, "rule": stripped})

    return {"zone": zone, "found": True, "rules": rules, "raw_output": out}


async def create_zone(name: str, *, interfaces: list[str] | None = None) -> dict:
    """Create a new firewall zone with default filter chains.

    Creates an nftables inet table and adds ``input``, ``forward``,
    and ``output`` chains with default accept policy.

    Args:
        name: The zone name (used as the nftables table name).
        interfaces: Optional list of interfaces (for informational
            message only; interface binding is not applied).

    Returns:
        A dictionary with ``success`` (bool) and ``message``.
    """
    out, rc = await _run(f"nft add table inet {shlex.quote(name)}", sudo=True)
    if rc != 0:
        return {"success": False, "message": out}

    # Add default input/forward/output chains
    for chain in ("input", "forward", "output"):
        hook_type = "filter"
        await _run(
            f"nft add chain inet {shlex.quote(name)} {chain} "
            f"{{ type {hook_type} hook {chain} priority 0 \\; policy accept \\; }}",
            sudo=True,
        )

    msg = f"Zone '{name}' created"
    if interfaces:
        msg += f" with interfaces: {', '.join(interfaces)}"

    return {"success": True, "message": msg}


async def delete_zone(name: str) -> dict:
    """Delete a firewall zone (nftables inet table).

    Args:
        name: The zone name to delete.

    Returns:
        A dictionary with ``success`` (bool) and ``message``.
    """
    out, rc = await _run(f"nft delete table inet {shlex.quote(name)}", sudo=True)
    msg = (
        (out or f"Zone '{name}' deleted")
        if rc == 0
        else f"Failed to delete zone '{name}': {out}"
    )
    return {"success": rc == 0, "message": msg}
