"""Firewall group management — nftables named sets.

Manages reusable address, network, and port groups (nftables sets)
that can be referenced in firewall rules.  Provides CRUD operations
for creating, listing, populating, and deleting named sets.

The sets live in the ``inet filter`` table which is auto-created if
it does not already exist.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex

log = logging.getLogger(__name__)

TABLE = "inet filter"


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
        log.warning("fw-group cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def _ensure_table() -> None:
    """Create the ``inet filter`` table if it does not exist.

    nftables ``add table`` is idempotent — it succeeds silently when
    the table already exists, so this is safe to call on every write
    operation.
    """
    _, rc = await _run(f"nft add table {TABLE}", sudo=True)
    if rc != 0:
        raise RuntimeError(
            f"Cannot create nftables table '{TABLE}' — check sudo permissions"
        )


async def list_groups() -> dict:
    """List all firewall groups (nftables named sets).

    Returns:
        A dictionary with ``count``, ``groups`` (list of set dicts
        with ``name``, ``type``, ``elements``), and ``raw_output``.
    """
    out, rc = await _run("nft list sets", sudo=True)
    if rc != 0:
        return {"count": 0, "groups": [], "raw_output": out}

    groups: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        m = re.match(r"\s*set\s+(\S+)\s*\{", line)
        if m:
            current = {"name": m.group(1), "type": "", "elements": []}
            continue
        if current:
            tm = re.match(r"\s*type\s+(\S+)", line)
            if tm:
                current["type"] = tm.group(1)
            em = re.match(r"\s*elements\s*=\s*\{(.+)\}", line)
            if em:
                current["elements"] = [
                    e.strip() for e in em.group(1).split(",") if e.strip()
                ]
            if line.strip() == "}":
                groups.append(current)
                current = None

    return {"count": len(groups), "groups": groups, "raw_output": out}


async def create_group(
    name: str, group_type: str, *, elements: list[str] | None = None
) -> dict:
    """Create a firewall group (nftables named set).

    Auto-creates the ``inet filter`` table when it does not exist.

    Args:
        name: Set name.
        group_type: One of ``address``, ``network``, or ``port``.
        elements: Optional initial elements to add to the set.

    Returns:
        A dictionary with ``success``, ``message``, ``name``, and ``type``.

    Raises:
        ValueError: If *group_type* is not a valid type.
        RuntimeError: If the nftables command fails.
    """
    nft_type_map = {
        "address": "ipv4_addr",
        "network": "ipv4_addr",
        "port": "inet_service",
    }
    nft_type = nft_type_map.get(group_type)
    if not nft_type:
        raise ValueError(
            f"Invalid group type '{group_type}'. Valid: address, network, port"
        )

    await _ensure_table()

    flags = "flags interval \\;" if group_type == "network" else ""
    safe_name = shlex.quote(name)
    out, rc = await _run(
        f"nft add set {TABLE} {safe_name} {{ type {nft_type} \\; {flags} }}",
        sudo=True,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to create group '{name}': {out}")

    if elements:
        elem_str = ", ".join(shlex.quote(e) for e in elements)
        eout, erc = await _run(
            f"nft add element {TABLE} {safe_name} {{ {elem_str} }}",
            sudo=True,
        )
        if erc != 0:
            raise RuntimeError(f"Group created but failed to add elements: {eout}")

    return {
        "success": True,
        "message": f"Group '{name}' created",
        "name": name,
        "type": group_type,
    }


async def delete_group(name: str) -> dict:
    """Delete a firewall group (nftables named set).

    Args:
        name: The set name to delete.

    Returns:
        A dictionary with ``success`` (bool) and ``message``.

    Raises:
        RuntimeError: If the nftables command fails.
    """
    out, rc = await _run(f"nft delete set {TABLE} {shlex.quote(name)}", sudo=True)
    if rc != 0:
        raise RuntimeError(f"Failed to delete group '{name}': {out}")
    return {
        "success": True,
        "message": f"Group '{name}' deleted",
    }


async def add_members(name: str, elements: list[str]) -> dict:
    """Add elements to an existing firewall group.

    Args:
        name: The set name to add elements to.
        elements: List of addresses, networks, or ports to add.

    Returns:
        A dictionary with ``success`` (bool) and ``message``.

    Raises:
        RuntimeError: If the nftables command fails.
    """
    elem_str = ", ".join(shlex.quote(e) for e in elements)
    out, rc = await _run(
        f"nft add element {TABLE} {shlex.quote(name)} {{ {elem_str} }}",
        sudo=True,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to add members to '{name}': {out}")
    return {
        "success": True,
        "message": f"Added {len(elements)} element(s) to '{name}'",
    }
