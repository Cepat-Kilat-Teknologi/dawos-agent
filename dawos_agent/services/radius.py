"""RADIUS diagnostics service.

Provides read-only views of the RADIUS configuration from
``accel-ppp.conf`` and live runtime statistics from ``accel-cmd``.
Includes a reachability check that performs a lightweight TCP connect
to each configured RADIUS server's authentication port.

**Security note:** shared secrets present in ``server=`` /
``auth-server=`` / ``acct-server=`` lines are **never** returned to
callers — only addresses and port numbers are extracted.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from ..config import ACCEL_CONFIG
from ..services import accel

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

#: Regex to extract address and optional port fields from a RADIUS server
#: directive.  The shared secret (second CSV field) is intentionally
#: ignored.
#:
#: Matches lines like:
#:   server=10.0.0.1,secret,auth-port=1812,acct-port=1813
#:   auth-server=10.0.0.1,secret,auth-port=1812
#:   acct-server=10.0.0.1,secret,acct-port=1813
_RE_SERVER_LINE = re.compile(
    r"^(?:server|auth-server|acct-server)\s*=\s*"
    r"([^,\s]+)"  # group 1: address (never contains comma/space)
)


def _parse_server_line(line: str) -> dict[str, Any] | None:
    """Parse one ``server=`` / ``auth-server=`` / ``acct-server=`` line.

    Returns a dict with ``address``, ``auth_port``, ``acct_port`` or
    ``None`` if the line doesn't match.  The shared secret is
    **intentionally discarded**.
    """
    match = _RE_SERVER_LINE.match(line.strip())
    if not match:
        return None

    address = match.group(1)
    auth_port = 1812
    acct_port = 1813

    # Extract optional port overrides from the tail of the line.
    port_auth = re.search(r"auth-port\s*=\s*(\d+)", line)
    if port_auth:
        auth_port = int(port_auth.group(1))

    port_acct = re.search(r"acct-port\s*=\s*(\d+)", line)
    if port_acct:
        acct_port = int(port_acct.group(1))

    return {"address": address, "auth_port": auth_port, "acct_port": acct_port}


def parse_radius_config(text: str) -> dict[str, Any]:
    """Parse the ``[radius]`` section from an accel-ppp config string.

    Only the ``[radius]`` section is examined.  Shared secrets embedded
    in ``server=`` lines are **never** included in the output.

    Args:
        text: Full ``accel-ppp.conf`` file content.

    Returns:
        A dictionary suitable for constructing
        :class:`~dawos_agent.models.schemas.RadiusConfigResponse`.
    """
    result: dict[str, Any] = {
        "nas_identifier": "",
        "nas_ip_address": "",
        "gw_ip_address": "",
        "servers": [],
        "timeout": 3,
        "max_try": 3,
        "acct_timeout": 0,
    }

    in_radius = False
    seen_addresses: set[str] = set()

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        # Section headers
        if stripped.startswith("["):
            in_radius = stripped.lower() == "[radius]"
            continue

        if not in_radius or not stripped or stripped.startswith("#"):
            continue

        # Simple key=value scalars
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            key = key.strip().lower()
            val = val.strip()

            if key == "nas-identifier":
                result["nas_identifier"] = val
            elif key == "nas-ip-address":
                result["nas_ip_address"] = val
            elif key == "gw-ip-address":
                result["gw_ip_address"] = val
            elif key == "timeout":
                result["timeout"] = int(val) if val.isdigit() else 3
            elif key == "max-try":
                result["max_try"] = int(val) if val.isdigit() else 3
            elif key == "acct-timeout":
                result["acct_timeout"] = int(val) if val.isdigit() else 0

            # Server lines (may appear multiple times)
            server = _parse_server_line(stripped)
            if server and server["address"] not in seen_addresses:
                seen_addresses.add(server["address"])
                result["servers"].append(server)

    return result


async def read_radius_config() -> dict[str, Any]:
    """Read the accel-ppp config file and parse its ``[radius]`` section.

    Returns:
        Parsed RADIUS configuration (no secrets).

    Raises:
        FileNotFoundError: If the config file does not exist.
    """
    text = ACCEL_CONFIG.read_text(encoding="utf-8")
    return parse_radius_config(text)


# ---------------------------------------------------------------------------
# Runtime status
# ---------------------------------------------------------------------------


async def get_radius_status() -> dict[str, Any]:
    """Retrieve live RADIUS server statistics from ``accel-cmd show stat``.

    Returns:
        A dict with ``servers`` list, ``total``, ``active``, ``down``.
    """
    data = await accel.show_stat_extended()
    servers: list[dict[str, Any]] = data.get("radius", [])
    active = sum(1 for s in servers if s.get("state") == "active")
    return {
        "servers": servers,
        "total": len(servers),
        "active": active,
        "down": len(servers) - active,
    }


# ---------------------------------------------------------------------------
# Reachability check
# ---------------------------------------------------------------------------

_CHECK_TIMEOUT: float = 3.0


async def _tcp_reachable(host: str, port: int) -> bool:
    """Test whether a TCP connection to *host*:*port* succeeds.

    Returns ``True`` if the three-way handshake completes within the
    timeout window, ``False`` otherwise.  No data is sent.
    """
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=_CHECK_TIMEOUT,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def check_radius() -> dict[str, Any]:
    """Run a full RADIUS diagnostic check.

    For every server found in the config file, checks:

    1. **Reachability** — TCP connect to the authentication port.
    2. **Runtime state** — queries ``accel-cmd show stat`` for the
       server's current state (``active`` / ``down``).

    Returns:
        A dict suitable for constructing
        :class:`~dawos_agent.models.schemas.RadiusCheckResponse`.
    """
    try:
        cfg = await read_radius_config()
    except FileNotFoundError:
        return {"checks": [], "total": 0, "healthy": False}

    # Build address → runtime-state map from live stats
    try:
        status = await get_radius_status()
    except RuntimeError:
        status = {"servers": []}

    state_map: dict[str, str] = {}
    for srv in status.get("servers", []):
        addr = srv.get("server_address", "")
        if addr:
            state_map[addr] = srv.get("state", "unknown")

    # Check each configured server concurrently
    config_servers: list[dict[str, Any]] = cfg.get("servers", [])
    checks: list[dict[str, Any]] = []

    reach_tasks = [_tcp_reachable(s["address"], s["auth_port"]) for s in config_servers]
    results = await asyncio.gather(*reach_tasks, return_exceptions=True)

    for srv, reachable in zip(config_servers, results):
        addr = srv["address"]
        port = srv["auth_port"]
        is_reachable = reachable is True
        state = state_map.get(addr, "unknown")

        if is_reachable and state == "active":
            detail = f"{addr}:{port} reachable, state active"
        elif is_reachable:
            detail = f"{addr}:{port} reachable, state {state}"
        else:
            detail = f"{addr}:{port} unreachable"

        checks.append(
            {
                "address": addr,
                "auth_port": port,
                "reachable": is_reachable,
                "state": state,
                "detail": detail,
            }
        )

    healthy = bool(checks) and all(
        c["reachable"] and c["state"] == "active" for c in checks
    )

    return {
        "checks": checks,
        "total": len(checks),
        "healthy": healthy,
    }
