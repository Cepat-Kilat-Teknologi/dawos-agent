"""BNG health diagnostics service.

Runs a battery of system checks and returns pass/warn/fail results for
the BNG host.  Covers accel-ppp service health, PPPoE module presence,
NAT configuration, firewall status, conntrack sizing, IP pool
availability, internet reachability, and SNMP daemon state.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import logging
import socket

from ..config import settings
from ..constants import CONNTRACK_RECOMMENDED_MIN, SNMPD_PORT

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


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


async def check_service() -> dict:
    """Check whether the accel-ppp systemd service is active.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    _, rc = await _run("systemctl is-active accel-ppp")
    if rc == 0:
        return {"name": "service", "status": "ok", "detail": "accel-ppp running"}
    return {"name": "service", "status": "fail", "detail": "accel-ppp not running"}


async def check_pppoe() -> dict:
    """Check whether the PPPoE kernel module is loaded.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    out, rc = await _run("lsmod | grep pppoe")
    if rc == 0 and "pppoe" in out:
        return {"name": "pppoe", "status": "ok", "detail": "pppoe module loaded"}
    return {"name": "pppoe", "status": "warn", "detail": "pppoe module not found"}


async def check_nat() -> dict:
    """Check whether NAT masquerade rules exist in the nftables ruleset.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    out, rc = await _run("nft list ruleset 2>/dev/null", sudo=True)
    if rc == 0 and "masquerade" in out:
        return {"name": "nat", "status": "ok", "detail": "NAT masquerade active"}
    return {"name": "nat", "status": "warn", "detail": "No NAT masquerade found"}


async def check_firewall() -> dict:
    """Check whether the nftables systemd service is active.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    _, rc = await _run("systemctl is-active nftables")
    if rc == 0:
        return {"name": "firewall", "status": "ok", "detail": "nftables active"}
    return {"name": "firewall", "status": "warn", "detail": "nftables not active"}


async def check_conntrack() -> dict:
    """Check whether nf_conntrack_max meets the recommended minimum.

    A value of at least 262 144 is recommended for BNG workloads.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    out, rc = await _run("sysctl -n net.netfilter.nf_conntrack_max")
    if rc != 0:
        return {
            "name": "conntrack",
            "status": "warn",
            "detail": "conntrack not available",
        }
    val = int(out.strip()) if out.strip().isdigit() else 0
    if val >= CONNTRACK_RECOMMENDED_MIN:
        return {
            "name": "conntrack",
            "status": "ok",
            "detail": f"nf_conntrack_max={val}",
        }
    return {
        "name": "conntrack",
        "status": "warn",
        "detail": f"nf_conntrack_max={val} (recommend ≥{CONNTRACK_RECOMMENDED_MIN})",
    }


async def check_pool() -> dict:
    """Check whether the accel-ppp IP pool has available addresses.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    from . import accel  # pylint: disable=import-outside-toplevel

    try:
        pool = await accel.show_ippool()
        avail = int(pool.get("available", "0"))
        total = int(pool.get("total", "0"))
        if total == 0:
            return {"name": "pool", "status": "warn", "detail": "No IP pool configured"}
        if avail == 0:
            return {
                "name": "pool",
                "status": "fail",
                "detail": f"IP pool exhausted (0/{total})",
            }
        return {
            "name": "pool",
            "status": "ok",
            "detail": f"{avail}/{total} addresses available",
        }
    except Exception as exc:
        return {"name": "pool", "status": "warn", "detail": str(exc)}


async def check_internet() -> dict:
    """Check internet connectivity by pinging the configured target.

    The target host defaults to ``8.8.8.8`` and can be overridden via
    the ``DAWOS_PING_TARGET`` environment variable.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    target = settings.ping_target
    _, rc = await _run(f"ping -c 1 -W 3 {target}")
    if rc == 0:
        return {"name": "internet", "status": "ok", "detail": "Internet reachable"}
    return {"name": "internet", "status": "fail", "detail": f"Cannot reach {target}"}


async def check_snmp() -> dict:
    """Check whether the SNMP daemon is running and UDP port 161 is reachable.

    Returns:
        A diagnostic result dict with ``name``, ``status``, and ``detail``.
    """
    _, rc = await _run("systemctl is-active snmpd")
    running = rc == 0

    port_open = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.bind(("127.0.0.1", 0))
            s.sendto(b"\x00", ("127.0.0.1", SNMPD_PORT))
            port_open = True
    except OSError:
        pass

    if running and port_open:
        return {
            "name": "snmp",
            "status": "ok",
            "detail": f"snmpd running, port {SNMPD_PORT} open",
        }
    if running:
        return {
            "name": "snmp",
            "status": "warn",
            "detail": f"snmpd running, port {SNMPD_PORT} closed",
        }
    return {"name": "snmp", "status": "warn", "detail": "snmpd not running"}


# ---------------------------------------------------------------------------
# Conntrack tuning
# ---------------------------------------------------------------------------


async def get_conntrack() -> dict:
    """Read the current nf_conntrack_max value and evaluate its adequacy.

    Returns:
        A dictionary with ``current_max``, ``recommended_min``,
        ``status``, and ``detail``.
    """
    out, rc = await _run("sysctl -n net.netfilter.nf_conntrack_max")
    if rc != 0:
        return {
            "current_max": 0,
            "recommended_min": CONNTRACK_RECOMMENDED_MIN,
            "status": "warn",
            "detail": "conntrack not available",
        }
    val = int(out.strip()) if out.strip().isdigit() else 0
    status = "ok" if val >= CONNTRACK_RECOMMENDED_MIN else "warn"
    detail = f"nf_conntrack_max={val}"
    if status == "warn":
        detail += f" (recommend ≥{CONNTRACK_RECOMMENDED_MIN})"
    return {
        "current_max": val,
        "recommended_min": CONNTRACK_RECOMMENDED_MIN,
        "status": status,
        "detail": detail,
    }


async def set_conntrack(max_value: int) -> dict:
    """Set nf_conntrack_max and persist the value via sysctl.d.

    Args:
        max_value: The new maximum number of conntrack entries.

    Returns:
        The updated conntrack status (same as :func:`get_conntrack`).
    """
    await _run(
        f"sysctl -w net.netfilter.nf_conntrack_max={max_value}",
        sudo=True,
    )
    # Persist
    await _run(
        f"tee /etc/sysctl.d/90-conntrack.conf > /dev/null "
        f"<<< 'net.netfilter.nf_conntrack_max = {max_value}'",
        sudo=True,
    )
    return await get_conntrack()


# ---------------------------------------------------------------------------
# SNMP status
# ---------------------------------------------------------------------------


async def snmp_status() -> dict:
    """Return the SNMP daemon status.

    Returns:
        A diagnostic result dict (delegates to :func:`check_snmp`).
    """
    return await check_snmp()


# ---------------------------------------------------------------------------
# Doctor — run all checks
# ---------------------------------------------------------------------------


async def run_doctor() -> dict:
    """Run all diagnostic checks concurrently and return a summary.

    Returns:
        A dictionary with ``checks`` (list), ``total``, ``fails``,
        ``warns``, and ``healthy`` (bool — True when no failures).
    """
    checks = await asyncio.gather(
        check_service(),
        check_pppoe(),
        check_nat(),
        check_firewall(),
        check_conntrack(),
        check_pool(),
        check_internet(),
        check_snmp(),
    )

    checks_list = list(checks)
    fails = sum(1 for c in checks_list if c["status"] == "fail")
    warns = sum(1 for c in checks_list if c["status"] == "warn")

    return {
        "checks": checks_list,
        "total": len(checks_list),
        "fails": fails,
        "warns": warns,
        "healthy": fails == 0,
    }
