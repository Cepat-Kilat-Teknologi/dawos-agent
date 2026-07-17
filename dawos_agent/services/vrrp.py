"""VRRP high-availability management service.

Wraps ``keepalived`` to expose Virtual Router Redundancy Protocol
status, VRRP group inspection, failover triggering, and service
restart for BNG redundancy setups.
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
        log.warning("vrrp cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def vrrp_status() -> dict:
    """Return the VRRP / keepalived status and discovered groups.

    Parses ``/tmp/keepalived.stats`` when keepalived is active.

    Returns:
        A dictionary with ``active`` (bool), ``service``, ``groups``
        (list of dicts with ``name``, ``state``, ``priority``, ``vip``),
        and ``raw_output``.
    """
    out, rc = await _run("systemctl is-active keepalived")
    active = rc == 0 and "active" in out

    groups: list[dict] = []
    if active:
        detail, drc = await _run("cat /tmp/keepalived.stats")
        if drc == 0 and detail:
            current: dict | None = None
            for line in detail.splitlines():
                m = re.match(r"VRRP Instance:\s+(\S+)", line)
                if m:
                    if current:
                        groups.append(current)
                    current = {
                        "name": m.group(1),
                        "state": "",
                        "priority": 0,
                        "vip": "",
                    }
                    continue
                if current:
                    sm = re.match(r"\s+State:\s+(\S+)", line)
                    if sm:
                        current["state"] = sm.group(1)
                    pm = re.match(r"\s+Priority:\s+(\d+)", line)
                    if pm:
                        current["priority"] = int(pm.group(1))
                    vm = re.match(r"\s+Virtual IP:\s+(\S+)", line)
                    if vm:
                        current["vip"] = vm.group(1)
            if current:
                groups.append(current)

    return {
        "active": active,
        "service": "keepalived",
        "groups": groups,
        "raw_output": out,
    }


async def vrrp_group_detail(group: str) -> dict:
    """Get details for a specific VRRP group.

    Args:
        group: The VRRP instance/group name.

    Returns:
        A dictionary with ``found`` (bool) and ``group`` (dict or None).
    """
    status = await vrrp_status()
    for g in status.get("groups", []):
        if g["name"] == group:
            return {"found": True, "group": g}
    return {"found": False, "group": None}


async def vrrp_failover(group: str) -> dict:
    """Trigger a VRRP failover by sending USR1 to keepalived.

    Args:
        group: The VRRP group name for context in the response.

    Returns:
        A dictionary with ``success`` (bool), ``group``, and ``message``.
    """
    # Read PID and send USR1 signal in two steps to avoid shell features.
    pid_out, pid_rc = await _run("cat /var/run/keepalived.pid")
    if pid_rc != 0 or not pid_out.strip():
        return {
            "success": False,
            "group": group,
            "message": "Cannot read keepalived PID file",
        }
    out, rc = await _run(
        f"kill -USR1 {pid_out.strip()}",
        sudo=True,
    )
    return {
        "success": rc == 0,
        "group": group,
        "message": out or f"Failover triggered for '{group}'",
    }


async def vrrp_restart() -> dict:
    """Restart the keepalived service via systemd.

    Returns:
        A dictionary with ``success`` (bool) and ``message``.
    """
    out, rc = await _run("systemctl restart keepalived", sudo=True)
    return {"success": rc == 0, "message": out or "keepalived restarted"}
