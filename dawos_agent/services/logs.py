"""Log retrieval and streaming service.

Wraps ``journalctl`` to provide log tail retrieval and real-time SSE
(Server-Sent Events) streaming for live log monitoring of accel-ppp
and other systemd service units on the BNG host.
"""

from __future__ import annotations

import asyncio
import json
import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(cmd: str) -> tuple[str, int]:
    """Execute a shell command asynchronously.

    Args:
        cmd: The command string to execute.

    Returns:
        A tuple of (stdout_text, return_code).
    """
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
# Tail
# ---------------------------------------------------------------------------


async def get_logs(
    lines: int = 100,
    unit: str = "accel-ppp",
) -> dict:
    """Retrieve the last *lines* log entries from journald for a service.

    Args:
        lines: Number of log lines to return (default 100).
        unit: The systemd unit name to query (default ``accel-ppp``).

    Returns:
        A dictionary with ``lines`` (list of strings), ``count``,
        and ``source`` (unit name).

    Raises:
        RuntimeError: If the journalctl command fails.
    """
    out, rc = await _run(
        f"journalctl -u {unit} --no-pager -n {lines}",
    )
    if rc != 0:
        raise RuntimeError(f"Failed to read logs: {out}")

    log_lines = out.splitlines() if out else []
    return {
        "lines": log_lines,
        "count": len(log_lines),
        "source": unit,
    }


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


async def log_stream_events(
    unit: str = "accel-ppp",
):
    """Async generator yielding SSE-formatted live log lines.

    Uses ``journalctl -f`` (follow mode) to stream new journal entries
    in real time.  Each yielded string is a complete SSE ``data:`` frame.

    Args:
        unit: The systemd unit name to follow (default ``accel-ppp``).

    Yields:
        SSE-formatted strings containing JSON log line data.
    """
    cmd = f"journalctl -u {unit} --no-pager -f -n 0"
    log.debug("exec (stream): %s", cmd)

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        assert proc.stdout is not None  # noqa: S101
        async for raw_line in proc.stdout:
            line = raw_line.decode().rstrip()
            if line:
                yield _sse({"line": line, "source": unit})
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(data: dict) -> str:
    """Format a dictionary as an SSE ``data:`` frame.

    Args:
        data: The payload to serialise as JSON.

    Returns:
        A string in SSE format ending with a double newline.
    """
    return f"data: {json.dumps(data)}\n\n"
