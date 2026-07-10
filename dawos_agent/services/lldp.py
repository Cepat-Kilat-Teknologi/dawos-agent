"""LLDP neighbor discovery service.

Wraps ``lldpcli`` to expose Link Layer Discovery Protocol neighbor
information via structured JSON output.  Provides status checks,
neighbor enumeration across all interfaces, and per-interface queries.
"""

from __future__ import annotations

import asyncio
import json
import logging
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
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("lldp cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def lldp_status() -> dict:
    """Check whether the LLDP daemon is running.

    Returns:
        A dictionary with ``running`` (bool) and ``raw_output``.
    """
    out, rc = await _run("lldpcli show configuration", sudo=True)
    if rc != 0:
        return {"running": False, "raw_output": out}

    return {"running": True, "raw_output": out}


async def lldp_neighbors() -> dict:
    """List LLDP neighbors discovered on all interfaces.

    Parses the JSON output from ``lldpcli show neighbors``.

    Returns:
        A dictionary with ``count``, ``neighbors`` (list of dicts with
        ``local_interface``, ``chassis_name``, ``port_id``,
        ``port_description``, ``ttl``), and ``raw_output``.
    """
    out, rc = await _run("lldpcli show neighbors -f json", sudo=True)
    if rc != 0:
        return {"count": 0, "neighbors": [], "raw_output": out}

    neighbors: list[dict] = []
    try:
        data = json.loads(out)
        lldp = data.get("lldp", {})
        interfaces = lldp.get("interface", [])
        # lldpcli returns either a list or a single dict
        if isinstance(interfaces, dict):
            interfaces = [interfaces]
        for iface in interfaces:
            if not isinstance(iface, dict):
                continue
            for if_name, details in iface.items():
                chassis = details.get("chassis", {})
                port = details.get("port", {})
                neighbors.append(
                    {
                        "local_interface": if_name,
                        "chassis_name": _extract_chassis_name(chassis),
                        "port_id": _extract_port_id(port),
                        "port_description": port.get("descr", ""),
                        "ttl": str(details.get("ttl", "")),
                    }
                )
    except (json.JSONDecodeError, TypeError, KeyError):
        # Fall back to raw output
        pass

    return {
        "count": len(neighbors),
        "neighbors": neighbors,
        "raw_output": out,
    }


async def lldp_interface(name: str) -> dict:
    """Get LLDP neighbor information for a specific interface.

    Args:
        name: The interface name to query (e.g. ``eth0``).

    Returns:
        A dictionary with ``interface``, ``found`` (bool),
        ``neighbors`` (list), and ``raw_output``.
    """
    out, rc = await _run(
        f"lldpcli show neighbors ports {shlex.quote(name)} -f json",
        sudo=True,
    )
    if rc != 0:
        return {"interface": name, "found": False, "neighbors": [], "raw_output": out}

    neighbors: list[dict] = []
    try:
        data = json.loads(out)
        lldp = data.get("lldp", {})
        interfaces = lldp.get("interface", [])
        if isinstance(interfaces, dict):
            interfaces = [interfaces]
        for iface in interfaces:
            if not isinstance(iface, dict):
                continue
            for if_name, details in iface.items():
                chassis = details.get("chassis", {})
                port = details.get("port", {})
                neighbors.append(
                    {
                        "local_interface": if_name,
                        "chassis_name": _extract_chassis_name(chassis),
                        "port_id": _extract_port_id(port),
                        "port_description": port.get("descr", ""),
                    }
                )
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return {
        "interface": name,
        "found": len(neighbors) > 0,
        "neighbors": neighbors,
        "raw_output": out,
    }


def _extract_chassis_name(chassis: dict) -> str:
    """Extract the chassis name from an lldpcli chassis dictionary.

    Args:
        chassis: The ``chassis`` dict from lldpcli JSON output.

    Returns:
        The chassis name as a string, or empty string if not found.
    """
    if not isinstance(chassis, dict):
        return ""
    for _k, v in chassis.items():
        if isinstance(v, dict):
            return v.get("name", "")
    return ""


def _extract_port_id(port: dict) -> str:
    """Extract the port identifier from an lldpcli port dictionary.

    Args:
        port: The ``port`` dict from lldpcli JSON output.

    Returns:
        The port ID as a string.
    """
    pid = port.get("id", {})
    if isinstance(pid, dict):
        return pid.get("value", str(pid))
    return str(pid)
