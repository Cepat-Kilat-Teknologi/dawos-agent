"""DHCP server and relay management service.

Wraps ``dnsmasq`` (DHCP server) and ``dhcrelay`` (DHCP relay) to
provide status checks, lease inspection, and service control for
the BNG host's DHCP infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import re

log = logging.getLogger(__name__)

_LEASE_RE = re.compile(
    r"^(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$",
)


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
        log.warning("dhcp cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def dhcp_status() -> dict:
    """Check the DHCP server (dnsmasq) service status.

    Returns:
        A dictionary with ``active`` (bool), ``service`` name,
        ``lease_count``, and ``raw_output``.
    """
    out, rc = await _run("systemctl is-active dnsmasq")
    active = rc == 0 and "active" in out

    leases = await dhcp_leases()
    return {
        "active": active,
        "service": "dnsmasq",
        "lease_count": leases["count"],
        "raw_output": out,
    }


async def dhcp_leases() -> dict:
    """Parse active DHCP leases from the dnsmasq lease file.

    Returns:
        A dictionary with ``count``, ``leases`` (list of lease dicts
        with ``expires``, ``mac``, ``ip``, ``hostname``, ``client_id``),
        and ``raw_output``.
    """
    out, rc = await _run("cat /var/lib/misc/dnsmasq.leases")
    if rc != 0:
        return {"count": 0, "leases": [], "raw_output": out}

    leases: list[dict] = []
    for line in out.splitlines():
        m = _LEASE_RE.match(line.strip())
        if m:
            leases.append(
                {
                    "expires": int(m.group(1)),
                    "mac": m.group(2),
                    "ip": m.group(3),
                    "hostname": m.group(4),
                    "client_id": m.group(5),
                }
            )

    return {"count": len(leases), "leases": leases, "raw_output": out}


async def relay_status() -> dict:
    """Check the DHCP relay (dhcrelay) service status.

    Returns:
        A dictionary with ``active`` (bool), ``service`` name,
        ``config`` (interface and upstream servers), and ``raw_output``.
    """
    out, rc = await _run("systemctl is-active dhcrelay")
    active = rc == 0 and "active" in out

    config = {}
    cfg_out, cfg_rc = await _run("systemctl show dhcrelay --property=ExecStart")
    if cfg_rc == 0:
        # Extract relay server from ExecStart
        m = re.search(r"-i\s+(\S+)", cfg_out)
        config["interface"] = m.group(1) if m else ""
        servers = re.findall(r"(\d+\.\d+\.\d+\.\d+)", cfg_out)
        config["servers"] = servers

    return {
        "active": active,
        "service": "dhcrelay",
        "config": config,
        "raw_output": out,
    }


async def dhcp_restart() -> dict:
    """Restart the DHCP server (dnsmasq) via systemd.

    Returns:
        A dictionary with ``success`` (bool) and ``message``.
    """
    out, rc = await _run("systemctl restart dnsmasq", sudo=True)
    return {"success": rc == 0, "message": out or "DHCP server restarted"}


async def relay_restart() -> dict:
    """Restart the DHCP relay (dhcrelay) via systemd.

    Returns:
        A dictionary with ``success`` (bool) and ``message``.
    """
    out, rc = await _run("systemctl restart dhcrelay", sudo=True)
    return {"success": rc == 0, "message": out or "DHCP relay restarted"}
