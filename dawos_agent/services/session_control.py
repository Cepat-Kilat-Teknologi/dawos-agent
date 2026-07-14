"""PPPoE session control — granular session operations.

Extends the basic terminate from :mod:`accel` with session restart,
snapshot with traffic counters, session-ID / IP lookups, and
MAC-based bulk termination for BNG session management.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging
import shlex

from ..constants import COLUMNS_EXTENDED
from . import accel

log = logging.getLogger(__name__)


async def session_by_sid(sid: str) -> dict | None:
    """Find a session by its accel-ppp session ID.

    Args:
        sid: The accel-ppp session identifier.

    Returns:
        A dictionary with session fields, or ``None`` if not found.
    """
    output = await accel.run_cmd(
        f"show sessions match sid ^{shlex.quote(sid)}$ {COLUMNS_EXTENDED}"
    )
    rows = accel.parse_table(output)
    return rows[0] if rows else None


async def session_by_ip(ip: str) -> dict | None:
    """Find a session by its assigned IP address.

    Args:
        ip: The subscriber IP address.

    Returns:
        A dictionary with session fields, or ``None`` if not found.
    """
    output = await accel.run_cmd(
        f"show sessions match ip ^{shlex.quote(ip)}$ {COLUMNS_EXTENDED}"
    )
    rows = accel.parse_table(output)
    return rows[0] if rows else None


async def session_snapshot(username: str) -> dict:
    """Get detailed session info with traffic counters for a user.

    Args:
        username: The subscriber username.

    Returns:
        A dictionary with ``username``, ``found`` (bool), ``sessions``
        (list of dicts with traffic counters), and ``count``.
    """
    output = await accel.run_cmd(
        f"show sessions match username ^{shlex.quote(username)}$ {COLUMNS_EXTENDED}",
    )
    rows = accel.parse_table(output)
    return {
        "username": username,
        "found": len(rows) > 0,
        "sessions": rows,
        "count": len(rows),
    }


async def restart_session(username: str) -> dict:
    """Terminate a user session so the CPE reconnects automatically.

    Args:
        username: The subscriber username.

    Returns:
        A dictionary with ``success`` (bool), ``username``,
        ``previous_interface``, and ``message``.
    """
    ifname = await accel.ifname_of(username)
    if ifname is None:
        return {
            "success": False,
            "username": username,
            "message": f"No active session for {username}",
        }

    try:
        await accel.terminate_session(username=username)
    except RuntimeError as exc:
        log.warning("Failed to terminate session for %s: %s", username, exc)
        return {
            "success": False,
            "username": username,
            "message": f"Terminate failed for {username}",
        }

    log.info("Restarted session for %s (was on %s)", username, ifname)

    return {
        "success": True,
        "username": username,
        "previous_interface": ifname,
        "message": f"Session terminated on {ifname}, CPE should reconnect",
    }


async def drop_by_mac(mac: str) -> dict:
    """Terminate all sessions originating from a specific MAC address.

    Args:
        mac: The calling-station-id (MAC) to match.

    Returns:
        A dictionary with ``success`` (bool), ``dropped`` (count),
        and ``message``.
    """
    cols = "sid,ifname,username,calling-sid"
    output = await accel.run_cmd(f"show sessions {cols}")
    rows = accel.parse_table(output)

    targets = [r for r in rows if r.get("calling-sid", "") == mac]
    if not targets:
        return {"success": False, "dropped": 0, "message": f"No session from MAC {mac}"}

    for t in targets:
        try:
            await accel.terminate_session(ifname=t["ifname"])
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to terminate %s: %s", t["ifname"], exc)

    return {
        "success": True,
        "dropped": len(targets),
        "message": f"Dropped {len(targets)} session(s) from {mac}",
    }
