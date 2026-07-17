"""Live traffic monitoring and shaper management.

Provides per-user throughput sampling, SSE generators for real-time
traffic dashboards, and ``tc`` shaper inspection and modification for
active accel-ppp sessions on the BNG.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
from datetime import datetime, timezone

from . import accel

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Byte-counter sampling
# ---------------------------------------------------------------------------


async def sample_session_bytes(username: str) -> tuple[int, int] | None:
    """Return current byte counters for a user's live session.

    Args:
        username: The subscriber username.

    Returns:
        A tuple of ``(rx_bytes, tx_bytes)``, or ``None`` if the
        session does not exist.
    """
    output = await accel.run_cmd(
        f"show sessions match username ^{shlex.quote(username)}$ "
        "rx-bytes-raw,tx-bytes-raw",
    )
    rows = accel.parse_table(output)
    if not rows:
        return None
    rx = _safe_int(rows[0].get("rx-bytes-raw", "0"))
    tx = _safe_int(rows[0].get("tx-bytes-raw", "0"))
    return rx, tx


async def sample_all_sessions() -> list[dict]:
    """Return byte counters and metadata for every active session.

    Returns:
        A list of dicts with ``sid``, ``username``, ``ip``,
        ``rate-limit``, ``rx-bytes-raw``, and ``tx-bytes-raw``.
    """
    output = await accel.run_cmd(
        "show sessions sid,username,ip,rate-limit,rx-bytes-raw,tx-bytes-raw",
    )
    return accel.parse_table(output)


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------


def compute_throughput(
    prev: tuple[int, int],
    curr: tuple[int, int],
    elapsed: float,
) -> tuple[float, float]:
    """Compute throughput in Mbps from byte-counter deltas.

    ``tx`` = bytes the BNG sent to the client = *download* for the subscriber.
    ``rx`` = bytes the BNG received from the client = *upload*.

    Args:
        prev: Previous ``(rx_bytes, tx_bytes)`` sample.
        curr: Current ``(rx_bytes, tx_bytes)`` sample.
        elapsed: Seconds between the two samples.

    Returns:
        A tuple of ``(download_mbps, upload_mbps)``.
    """
    if elapsed <= 0:
        return 0.0, 0.0
    rx_delta = max(curr[0] - prev[0], 0)
    tx_delta = max(curr[1] - prev[1], 0)
    download = tx_delta * 8 / elapsed / 1e6
    upload = rx_delta * 8 / elapsed / 1e6
    return round(download, 2), round(upload, 2)


# ---------------------------------------------------------------------------
# SSE generators
# ---------------------------------------------------------------------------


async def user_traffic_events(
    username: str,
    interval: float = 2.0,
):
    """Async generator yielding SSE-formatted per-user traffic events.

    Computes download/upload throughput from byte-counter deltas at
    the specified interval.  Exits when the session disappears.

    Args:
        username: The subscriber username to monitor.
        interval: Sampling interval in seconds (default 2.0).

    Yields:
        SSE-formatted strings containing JSON traffic data.
    """
    prev = await sample_session_bytes(username)
    if prev is None:
        yield _sse({"error": "no session found", "username": username})
        return

    await asyncio.sleep(interval)

    while True:
        curr = await sample_session_bytes(username)
        if curr is None:
            yield _sse({"error": "session ended", "username": username})
            return
        dl, ul = compute_throughput(prev, curr, interval)
        yield _sse(
            {
                "username": username,
                "download_mbps": dl,
                "upload_mbps": ul,
                "rx_bytes": curr[0],
                "tx_bytes": curr[1],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        prev = curr
        await asyncio.sleep(interval)


async def aggregate_traffic_events(interval: float = 2.0):
    """Async generator yielding SSE-formatted aggregate traffic for all sessions.

    Each event contains per-session throughput sorted by download
    descending, plus total throughput counters.  Exits when no
    sessions remain.

    Args:
        interval: Sampling interval in seconds (default 2.0).

    Yields:
        SSE-formatted strings containing JSON aggregate traffic data.
    """
    prev_map: dict[str, tuple[int, int]] = {}
    rows = await sample_all_sessions()
    if not rows:
        yield _sse({"error": "no active sessions"})
        return

    for r in rows:
        sid = r.get("sid", "")
        prev_map[sid] = (
            _safe_int(r.get("rx-bytes-raw", "0")),
            _safe_int(r.get("tx-bytes-raw", "0")),
        )

    await asyncio.sleep(interval)

    while True:
        rows = await sample_all_sessions()
        if not rows:
            yield _sse({"error": "no active sessions"})
            return

        samples = []
        total_dl, total_ul = 0.0, 0.0
        for r in rows:
            sid = r.get("sid", "")
            rx = _safe_int(r.get("rx-bytes-raw", "0"))
            tx = _safe_int(r.get("tx-bytes-raw", "0"))
            prev = prev_map.get(sid, (rx, tx))
            dl, ul = compute_throughput(prev, (rx, tx), interval)
            total_dl += dl
            total_ul += ul
            samples.append(
                {
                    "username": r.get("username", ""),
                    "ip": r.get("ip", ""),
                    "rate_limit": r.get("rate-limit", ""),
                    "download_mbps": dl,
                    "upload_mbps": ul,
                }
            )
            prev_map[sid] = (rx, tx)

        samples.sort(key=lambda s: s["download_mbps"], reverse=True)
        yield _sse(
            {
                "sessions": samples,
                "session_count": len(samples),
                "total_download_mbps": round(total_dl, 2),
                "total_upload_mbps": round(total_ul, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Queue / shaper
# ---------------------------------------------------------------------------


async def get_queue_stats(username: str) -> dict:
    """Return ``tc`` shaper statistics for a user's session interface.

    Args:
        username: The subscriber username.

    Returns:
        A dictionary with ``username``, ``ifname``, ``qdisc``,
        ``classes``, and ``filters``.

    Raises:
        ValueError: If no live session exists for the user.
    """
    ifname = await accel.ifname_of(username)
    if not ifname:
        raise ValueError(f"No live session for {username}")

    qdisc = await _tc(f"tc -s qdisc show dev {ifname}")
    classes = await _tc(f"tc -s class show dev {ifname}")
    filters = await _tc(
        f"tc -s filter show dev {ifname} parent ffff:",
    )
    return {
        "username": username,
        "ifname": ifname,
        "qdisc": qdisc,
        "classes": classes,
        "filters": filters,
    }


async def change_ratelimit(username: str, rate: str) -> str:
    """Change a session's shaper live, bypassing RADIUS.

    This is a temporary change that persists only until the session ends.

    Args:
        username: The subscriber username.
        rate: Rate string (e.g. ``"10M/5M"`` for down/up).

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If no live session exists for the user.
    """
    ifname = await accel.ifname_of(username)
    if not ifname:
        raise ValueError(f"No live session for {username}")
    if "/" in rate:
        up, down = rate.split("/", 1)
        shaper_value = f"{down}/{up}"
    else:
        shaper_value = rate
    await accel.shaper_change(ifname, shaper_value)
    return f"Shaper changed to {rate} for {username} ({ifname})"


async def restore_ratelimit(username: str) -> str:
    """Restore a session's shaper to the RADIUS-assigned value.

    Args:
        username: The subscriber username.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If no live session exists for the user.
    """
    ifname = await accel.ifname_of(username)
    if not ifname:
        raise ValueError(f"No live session for {username}")
    await accel.shaper_restore(ifname)
    return f"Shaper restored for {username} ({ifname})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _tc(cmd: str) -> str:
    """Run a ``tc`` command via sudo and return stdout.

    Args:
        cmd: The full ``tc`` command string.

    Returns:
        The stripped stdout text.
    """
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(f"sudo {cmd}"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


def _safe_int(value, default: int = 0) -> int:
    """Convert a value to an integer, returning *default* on failure.

    Args:
        value: The value to convert.
        default: Fallback value if conversion fails.

    Returns:
        The parsed integer or *default*.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _sse(data: dict) -> str:
    """Format a dictionary as an SSE ``data:`` frame.

    Args:
        data: The payload to serialise as JSON.

    Returns:
        A string in SSE format ending with a double newline.
    """
    return f"data: {json.dumps(data)}\n\n"
