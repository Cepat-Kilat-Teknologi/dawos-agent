"""accel-ppp control interface service.

Provides local subprocess access to ``accel-cmd`` for managing
the accel-ppp PPPoE concentrator running on this BNG host.  Supports
session queries, statistics, IP pool inspection, shaper control,
MAC filtering, and configuration reloads.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
from typing import Any

from ..config import settings
from ..constants import ACCEL_SESSION_COLUMNS, COLUMNS_DEFAULT
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

    proc = await asyncio.create_subprocess_exec(
        *shlex.split(full_cmd),
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


def validate_columns(columns: str) -> str:
    """Validate and sanitise a comma-separated column list.

    Each token is checked against :data:`ACCEL_SESSION_COLUMNS`.
    Unknown column names are silently dropped so that the resulting
    string is always safe for shell interpolation.

    Args:
        columns: Comma-separated column names from the caller.

    Returns:
        A sanitised comma-separated string containing only valid columns.

    Raises:
        ValueError: If *columns* is empty or contains no valid names.
    """
    valid = [
        c
        for c in (tok.strip() for tok in columns.split(","))
        if c in ACCEL_SESSION_COLUMNS
    ]
    if not valid:
        raise ValueError(f"No valid columns in: {columns}")
    return ",".join(valid)


async def show_sessions(
    columns: str = COLUMNS_DEFAULT,
) -> list[dict[str, str]]:
    """Retrieve all active PPPoE sessions as a list of dictionaries.

    Args:
        columns: Comma-separated column names to include in the output.
            Defaults to the legacy 10-column set for backward
            compatibility.  Pass :data:`COLUMNS_EXTENDED` for the full
            telemetry set.

    Returns:
        A list of dicts, one per session, keyed by column name.
    """
    safe_cols = validate_columns(columns)
    output = await run_cmd(f"show sessions {safe_cols}")
    return parse_table(output)


# -- Search match fields whitelist -------------------------------------------
SEARCH_MATCH_FIELDS: frozenset[str] = frozenset(
    {
        "ifname",
        "username",
        "ip",
        "calling-sid",
        "called-sid",
        "sid",
        "type",
        "state",
        "inbound-if",
        "service-name",
    }
)
"""Fields accepted by ``accel-cmd show sessions match <field>``."""


def validate_match_field(field: str) -> str:
    """Validate that *field* is an allowed ``show sessions match`` field.

    Args:
        field: The match field name.

    Returns:
        The validated field name.

    Raises:
        ValueError: If *field* is not in :data:`SEARCH_MATCH_FIELDS`.
    """
    if field not in SEARCH_MATCH_FIELDS:
        raise ValueError(f"Invalid match field: {field}")
    return field


async def search_sessions(
    field: str,
    value: str,
    columns: str = COLUMNS_DEFAULT,
) -> list[dict[str, str]]:
    """Search active sessions by matching a field value.

    Uses ``accel-cmd show sessions match <field> <value> <columns>``
    to find sessions where the given field matches the value.

    Args:
        field: The session field to match against (must be in
            :data:`SEARCH_MATCH_FIELDS`).
        value: The value or pattern to match.
        columns: Comma-separated column names to include in results.

    Returns:
        A list of session dicts matching the search criteria.

    Raises:
        ValueError: If *field* is invalid or *columns* contains no
            valid column names.
    """
    safe_field = validate_match_field(field)
    safe_cols = validate_columns(columns)
    output = await run_cmd(
        f"show sessions match {safe_field} {shlex.quote(value)} {safe_cols}"
    )
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
                # A different accel-ppp build may emit a non-numeric value
                # (e.g. "-"); keep the pre-initialised 0 default (DA-L02).
                with contextlib.suppress(ValueError):
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


async def show_stat_extended() -> dict[str, Any]:
    """Retrieve and parse complete accel-ppp runtime statistics.

    Unlike :func:`show_stat` which only extracts sessions/cpu/uptime,
    this function parses **every** section of ``show stat`` output
    including core, pppoe, radius, and memory.

    Returns:
        A dictionary suitable for constructing an
        :class:`~dawos_agent.models.schemas.ExtendedStatsResponse`.
    """
    output = await run_cmd("show stat")
    return parse_stat_extended(output)


def parse_stat_extended(  # pylint: disable=too-many-branches
    text: str,
) -> dict[str, Any]:
    """Parse the full ``show stat`` output into a structured dictionary.

    Handles all sections: uptime, cpu, mem, core, sessions, pppoe, and
    one or more ``radius(...)`` blocks.  The RADIUS header line uses a
    special format ``radius(<id>, <addr>):`` which is parsed to extract
    the server identifier and address.

    Args:
        text: Raw multi-line output from ``accel-cmd show stat``.

    Returns:
        A nested dictionary matching the
        :class:`~dawos_agent.models.schemas.ExtendedStatsResponse` shape.
    """
    result: dict[str, Any] = {
        "uptime": "",
        "cpu": "0",
        "memory": {"rss_kb": 0, "virt_kb": 0},
        "core": {},
        "sessions": {"starting": 0, "active": 0, "finishing": 0},
        "pppoe": {},
        "radius": [],
    }
    section: str | None = None
    current_radius: dict[str, Any] | None = None

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        # Top-level keys (no leading whitespace)
        if raw and not raw[0:1].isspace():
            # Flush any pending RADIUS block
            if current_radius is not None:
                result["radius"].append(current_radius)
                current_radius = None

            if stripped.startswith("uptime:"):
                result["uptime"] = stripped.split(":", 1)[1].strip()
                section = None
                continue
            if stripped.startswith("cpu:"):
                result["cpu"] = stripped.split(":", 1)[1].strip().rstrip("%")
                section = None
                continue
            if stripped.startswith("mem(rss/virt):"):
                _parse_mem_line(stripped, result)
                section = None
                continue

            # radius(3, 10.100.0.253):
            if stripped.startswith("radius("):
                current_radius = _parse_radius_header(stripped)
                section = "radius"
                continue

            # Simple section header: "core:", "sessions:", "pppoe:"
            if stripped.endswith(":") and " " not in stripped:
                section = stripped.rstrip(":")
            else:
                section = None
            continue

        # Indented line → belongs to current section
        if ":" not in stripped:
            continue

        key, val = stripped.split(":", 1)
        key = key.strip()
        val = val.strip()

        if section == "core":
            with contextlib.suppress(ValueError):
                result["core"][key] = int(val)
        elif section == "sessions":
            if key in ("starting", "active", "finishing"):
                with contextlib.suppress(ValueError):
                    result["sessions"][key] = int(val)
        elif section == "pppoe":
            _parse_pppoe_line(key, val, result)
        elif section == "radius" and current_radius is not None:
            _parse_radius_line(key, val, current_radius)

    # Flush final RADIUS block if output ended without a new section
    if current_radius is not None:
        result["radius"].append(current_radius)

    return result


def _parse_mem_line(line: str, result: dict[str, Any]) -> None:
    """Extract RSS and virtual memory from ``mem(rss/virt): X/Y kB``."""
    after_colon = line.split(":", 1)[1].strip()
    mem_part = after_colon.split()[0] if after_colon else ""
    parts = mem_part.split("/")
    if len(parts) == 2:
        with contextlib.suppress(ValueError):
            result["memory"]["rss_kb"] = int(parts[0])
        with contextlib.suppress(ValueError):
            result["memory"]["virt_kb"] = int(parts[1])


def _parse_radius_header(line: str) -> dict[str, Any]:
    """Parse ``radius(<id>, <addr>):`` into initial RADIUS dict."""
    rad: dict[str, Any] = {"server_id": "", "server_address": ""}
    # Extract content between parentheses
    start = line.index("(") + 1
    end = line.index(")")
    inner = line[start:end]
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) >= 1:
        rad["server_id"] = parts[0]
    if len(parts) >= 2:
        rad["server_address"] = parts[1]
    return rad


def _parse_pppoe_line(key: str, val: str, result: dict[str, Any]) -> None:
    """Parse a single PPPoE stats line into the result dict."""
    pppoe = result.setdefault("pppoe", {})
    simple_keys = {
        "starting": "starting",
        "active": "active",
        "delayed PADO": "delayed_pado",
        "recv PADI": "recv_padi",
        "drop PADI": "drop_padi",
        "sent PADO": "sent_pado",
        "sent PADS": "sent_pads",
        "filtered": "filtered",
    }
    if key in simple_keys:
        with contextlib.suppress(ValueError):
            pppoe[simple_keys[key]] = int(val)
        return

    # recv PADR(dup): 20041(0)
    if key.startswith("recv PADR"):
        _parse_padr(val, pppoe)


def _parse_padr(val: str, pppoe: dict[str, Any]) -> None:
    """Parse ``recv PADR(dup): 20041(0)`` value."""
    # val = "20041(0)"
    if "(" in val:
        main_part = val.split("(")[0]
        dup_part = val.split("(")[1].rstrip(")")
        with contextlib.suppress(ValueError):
            pppoe["recv_padr"] = int(main_part)
        with contextlib.suppress(ValueError):
            pppoe["recv_padr_dup"] = int(dup_part)
    else:
        with contextlib.suppress(ValueError):
            pppoe["recv_padr"] = int(val)


def _parse_radius_line(key: str, val: str, rad: dict[str, Any]) -> None:
    """Parse a single RADIUS stats line into the RADIUS dict."""
    simple = {
        "state": "state",
        "fail count": "fail_count",
        "request count": "request_count",
        "queue length": "queue_length",
        "auth sent": "auth_sent",
        "acct sent": "acct_sent",
        "interim sent": "interim_sent",
    }
    if key in simple:
        field = simple[key]
        if field == "state":
            rad[field] = val
        else:
            with contextlib.suppress(ValueError):
                rad[field] = int(val)
        return

    # auth lost(total/5m/1m): 414/0/0
    _parse_radius_lost(key, val, rad)
    # auth avg query time(5m/1m): 0/0 ms
    _parse_radius_avg(key, val, rad)


def _parse_radius_lost(key: str, val: str, rad: dict[str, Any]) -> None:
    """Parse ``<type> lost(total/5m/1m): X/Y/Z`` into RADIUS dict."""
    for prefix in ("auth", "acct", "interim"):
        label = f"{prefix} lost(total/5m/1m)"
        if key == label:
            parts = val.split("/")
            if len(parts) == 3:
                with contextlib.suppress(ValueError):
                    rad[f"{prefix}_lost_total"] = int(parts[0])
                with contextlib.suppress(ValueError):
                    rad[f"{prefix}_lost_5m"] = int(parts[1])
                with contextlib.suppress(ValueError):
                    rad[f"{prefix}_lost_1m"] = int(parts[2])
            return


def _parse_radius_avg(key: str, val: str, rad: dict[str, Any]) -> None:
    """Parse ``<type> avg query time(5m/1m): X/Y ms`` into RADIUS dict."""
    for prefix in ("auth", "acct", "interim"):
        label = f"{prefix} avg query time(5m/1m)"
        if key == label:
            clean = val.replace("ms", "").strip()
            parts = clean.split("/")
            if len(parts) == 2:
                with contextlib.suppress(ValueError):
                    rad[f"{prefix}_avg_query_time_5m"] = int(parts[0])
                with contextlib.suppress(ValueError):
                    rad[f"{prefix}_avg_query_time_1m"] = int(parts[1])
            return


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
