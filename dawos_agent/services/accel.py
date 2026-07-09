"""accel-ppp control interface service.

Provides local subprocess access to ``accel-cmd`` for managing
the accel-ppp PPPoE concentrator running on this BNG host.  Supports
session queries, statistics, IP pool inspection, shaper control,
MAC filtering, and configuration reloads.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any

from ..config import settings
from ..retry import with_retry

log = logging.getLogger(__name__)


async def run_cmd(args: str) -> str:
    """Execute an accel-cmd command and return its standard output.

    Constructs the full command as ``accel-cmd -p <port> <args>`` using
    the configured binary path and CLI port.  Transient failures
    (connection refused, timeout) are retried with exponential backoff
    according to ``DAWOS_RETRY_MAX`` and ``DAWOS_RETRY_DELAY`` settings.

    Args:
        args: Arguments to pass to ``accel-cmd``.

    Returns:
        The stripped stdout text from the command.

    Raises:
        RuntimeError: If the command exits with a non-zero return code
            after all retry attempts are exhausted.
    """
    return await with_retry(
        _run_cmd_once,
        args,
        max_retries=settings.retry_max,
        base_delay=settings.retry_delay,
    )


async def _run_cmd_once(args: str) -> str:
    """Execute a single accel-cmd attempt (no retry)."""
    full_cmd = f"{settings.accel_cmd} -p {settings.accel_cli_port} {args}"
    log.debug("exec: %s", full_cmd)

    proc = await asyncio.create_subprocess_shell(
        full_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip()

    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("accel-cmd failed (rc=%d): %s", proc.returncode, err)
        # Lazy import to avoid circular dependency at load time.
        from ..metrics import (  # pylint: disable=import-outside-toplevel
            ACCEL_CMD_ERRORS_TOTAL,
        )

        ACCEL_CMD_ERRORS_TOTAL.inc()
        raise RuntimeError(f"accel-cmd error: {err or output}")

    return output


async def show_sessions(
    columns: str = "ifname,username,ip,calling-sid,rate-limit,type,state,uptime,rx-bytes,tx-bytes",
) -> list[dict[str, str]]:
    """Retrieve all active PPPoE sessions as a list of dictionaries.

    Args:
        columns: Comma-separated column names to include in the output.

    Returns:
        A list of dicts, one per session, keyed by column name.
    """
    output = await run_cmd(f"show sessions {columns}")
    return parse_table(output)


async def show_stat() -> dict[str, Any]:
    """Retrieve and parse accel-ppp runtime statistics.

    Returns:
        A dictionary containing uptime, CPU usage, and session counts
        (starting, active, finishing).
    """
    output = await run_cmd("show stat")
    return parse_stat(output)


async def show_ippool() -> dict[str, str]:
    """Retrieve IP pool utilisation summary.

    Returns:
        A dictionary with ``used``, ``total``, and ``available`` counts.
    """
    output = await run_cmd("show ippool")
    return parse_ippool(output)


async def show_version() -> str:
    """Retrieve the accel-ppp daemon version string.

    Returns:
        The version string reported by ``accel-cmd show version``.
    """
    return await run_cmd("show version")


async def reload_config() -> str:
    """Reload the accel-ppp configuration without dropping active sessions.

    Returns:
        Command output confirming the reload.
    """
    return await run_cmd("reload")


async def terminate_session(
    *, username: str | None = None, ifname: str | None = None
) -> str:
    """Terminate a single PPPoE session by username or interface name.

    Args:
        username: Subscriber username to disconnect.
        ifname: PPP interface name (e.g. ``ppp0``) to disconnect.

    Returns:
        Command output confirming the termination.

    Raises:
        ValueError: If neither *username* nor *ifname* is provided.
    """
    if username:
        return await run_cmd(f"terminate username {shlex.quote(username)}")
    if ifname:
        return await run_cmd(f"terminate if {shlex.quote(ifname)}")
    raise ValueError("Either username or ifname must be provided")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_table(text: str) -> list[dict[str, str]]:
    """Parse pipe-delimited ``accel-cmd`` table output into a list of dicts.

    The first data row is used as column headers; subsequent rows are
    converted into dictionaries keyed by those headers.

    Args:
        text: Raw multi-line table output from ``accel-cmd``.

    Returns:
        A list of dictionaries, one per data row.
    """
    rows: list[dict[str, str]] = []
    cols: list[str] | None = None

    for line in text.splitlines():
        if "|" not in line or set(line) <= set("-+ "):
            continue
        cells = [c.strip() for c in line.split("|")]
        if cols is None:
            cols = cells
        elif len(cells) == len(cols):
            rows.append(dict(zip(cols, cells)))

    return rows


def parse_stat(text: str) -> dict[str, Any]:
    """Parse ``show stat`` output into a structured dictionary.

    The output contains multiple top-level sections (core, sessions,
    pppoe, etc.) that share key names like ``starting`` and ``active``.
    Only the ``sessions:`` block is extracted.  Section boundaries are
    detected via indentation: a non-indented line ending with ``:``
    opens a new section; indented ``key: value`` lines belong to the
    current section.

    Args:
        text: Raw multi-line output from ``accel-cmd show stat``.

    Returns:
        A dictionary with ``uptime``, ``cpu``, and ``sessions`` keys.
    """
    result: dict[str, Any] = {
        "uptime": "",
        "cpu": "0",
        "sessions": {"starting": 0, "active": 0, "finishing": 0},
    }
    section: str | None = None

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        # Top-level keys (no leading whitespace)
        if not raw[0:1].isspace() if raw else False:
            if stripped.startswith("uptime:"):
                result["uptime"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("cpu:"):
                result["cpu"] = stripped.split(":", 1)[1].strip().rstrip("%")
            # Section header — e.g. "sessions:", "pppoe:", "core:"
            if stripped.endswith(":") and " " not in stripped:
                section = stripped.rstrip(":")
            else:
                section = None
            continue

        # Indented line → belongs to current section
        if section == "sessions" and ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            if key in ("starting", "active", "finishing"):
                result["sessions"][key] = int(val.strip())

    return result


def parse_ippool(text: str) -> dict[str, str]:
    """Parse ``show ippool`` output into a utilisation dictionary.

    Args:
        text: Raw multi-line output from ``accel-cmd show ippool``.

    Returns:
        A dictionary with ``used``, ``total``, and ``available`` string values.
    """
    result: dict[str, str] = {"used": "0", "total": "0", "available": "0"}

    for line in text.splitlines():
        s = line.strip()
        for key in result:
            if s.startswith(f"{key}:"):
                result[key] = s.split(":", 1)[1].strip()

    return result


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


async def ifname_of(username: str) -> str | None:
    """Look up the PPP interface name for an active subscriber session.

    Args:
        username: The subscriber username to search for.

    Returns:
        The interface name (e.g. ``ppp0``), or ``None`` if the user
        has no active session.
    """
    output = await run_cmd(
        f"show sessions match username ^{shlex.quote(username)}$ ifname"
    )
    for line in output.splitlines():
        line = line.strip()
        if line and line != "ifname" and not set(line) <= set("-+ "):
            return line
    return None


# ---------------------------------------------------------------------------
# Shaper
# ---------------------------------------------------------------------------


async def shutdown(mode: str = "soft") -> str:
    """Initiate accel-ppp daemon shutdown.

    Args:
        mode: Shutdown strategy — ``"soft"`` stops accepting new
            connections and waits for all sessions to disconnect
            naturally (drain mode); ``"hard"`` terminates immediately.

    Returns:
        Command output confirming the shutdown initiation.
    """
    return await run_cmd(f"shutdown {shlex.quote(mode)}")


async def shutdown_cancel() -> str:
    """Cancel a soft shutdown and resume normal operation.

    Only effective after a ``shutdown soft`` — a hard shutdown cannot
    be cancelled because the daemon exits immediately.

    Returns:
        Command output confirming the cancellation.
    """
    return await run_cmd("shutdown cancel")


async def shaper_change(ifname: str, rate: str) -> str:
    """Temporarily change the traffic shaper rate for a live session.

    The change is not persisted and will revert on session reconnect.

    Args:
        ifname: PPP interface name (e.g. ``ppp0``).
        rate: Rate string in accel-ppp format (e.g. ``10000/5000``).

    Returns:
        Command output confirming the shaper change.
    """
    return await run_cmd(
        f"shaper change {shlex.quote(ifname)} {shlex.quote(rate)} temp"
    )


async def shaper_restore(ifname: str) -> str:
    """Restore a session's traffic shaper to the RADIUS-assigned value.

    Args:
        ifname: PPP interface name (e.g. ``ppp0``).

    Returns:
        Command output confirming the shaper restoration.
    """
    return await run_cmd(f"shaper restore {shlex.quote(ifname)}")


# ---------------------------------------------------------------------------
# MAC filter
# ---------------------------------------------------------------------------


async def mac_filter(action: str = "show", mac: str = "") -> str:
    """Manage the PPPoE MAC address filter.

    Args:
        action: Operation to perform — ``show``, ``add``, or ``del``.
        mac: MAC address to add or remove (ignored for ``show``).

    Returns:
        Command output showing the current filter state or confirmation
        of the add/delete operation.
    """
    cmd = f"pppoe mac-filter {action} {shlex.quote(mac)}".strip()
    return await run_cmd(cmd)
