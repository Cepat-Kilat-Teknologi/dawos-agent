"""NTP time synchronisation management service.

Wraps ``chronyc`` to expose NTP synchronisation status, source
enumeration, and drift monitoring via a structured API.
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
        log.warning("cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def ntp_status() -> dict:
    """Return NTP synchronisation status via ``chronyc tracking``.

    Returns:
        A dictionary with ``synced`` (bool), ``reference``, ``stratum``,
        ``system_time_offset``, ``last_offset``, ``frequency``, and
        ``raw_output``.
    """
    out, rc = await _run("chronyc tracking")
    if rc != 0:
        return {"synced": False, "raw_output": out}

    result: dict = {
        "synced": False,
        "reference": "",
        "stratum": 0,
        "system_time_offset": "",
        "last_offset": "",
        "frequency": "",
        "raw_output": out,
    }

    for line in out.splitlines():
        if line.startswith("Reference ID"):
            result["reference"] = line.split(":", 1)[1].strip()
        elif line.startswith("Stratum"):
            result["stratum"] = _safe_int(line.split(":", 1)[1].strip())
        elif line.startswith("System time"):
            result["system_time_offset"] = line.split(":", 1)[1].strip()
        elif line.startswith("Last offset"):
            result["last_offset"] = line.split(":", 1)[1].strip()
        elif line.startswith("Frequency"):
            result["frequency"] = line.split(":", 1)[1].strip()
        elif "Normal" in line or "synchronized" in line.lower():
            result["synced"] = True

    # chrony reports synced if stratum > 0 and reference is not 0.0.0.0
    if result["stratum"] > 0 and "0.0.0.0" not in result["reference"]:
        result["synced"] = True

    return result


async def ntp_sources() -> dict:
    """Return configured NTP sources via ``chronyc sources``.

    Returns:
        A dictionary with ``count``, ``sources`` (list of dicts with
        ``tally``, ``name``, ``stratum``, ``poll``, ``reach``,
        ``detail``), and ``raw_output``.
    """
    out, rc = await _run("chronyc sources")
    if rc != 0:
        return {"count": 0, "sources": [], "raw_output": out}

    sources: list[dict] = []
    for line in out.splitlines():
        # Source lines start with ^, * (selected), +, -, ?, x
        m = re.match(
            r"([*+\-?x^])\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.*)",
            line,
        )
        if m:
            sources.append(
                {
                    "tally": m.group(1),
                    "name": m.group(2),
                    "stratum": _safe_int(m.group(3)),
                    "poll": _safe_int(m.group(4)),
                    "reach": m.group(5),
                    "detail": m.group(6).strip(),
                }
            )

    return {"count": len(sources), "sources": sources, "raw_output": out}


def _safe_int(value: str, default: int = 0) -> int:
    """Convert a string to an integer, returning *default* on failure.

    Args:
        value: The string to convert.
        default: Fallback value if conversion fails.

    Returns:
        The parsed integer or *default*.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
