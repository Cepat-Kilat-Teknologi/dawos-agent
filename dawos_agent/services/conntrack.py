"""Connection tracking (nf_conntrack) management service.

Provides operations for inspecting and tuning the Linux nf_conntrack
subsystem on the BNG host.  Wraps ``sysctl`` and ``lsmod`` to expose
table size, protocol timeouts, loaded helper modules, and predefined
tuning profiles optimised for common ISP traffic patterns.
"""

from __future__ import annotations

import asyncio
import logging
import re

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
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


# ---------------------------------------------------------------------------
# Table config
# ---------------------------------------------------------------------------


async def get_config() -> dict:
    """Read the current nf_conntrack table configuration.

    Returns:
        A dictionary with ``table_size``, ``current_count``,
        ``hash_size``, and ``usage_percent``.
    """
    max_out, _ = await _run("sysctl -n net.netfilter.nf_conntrack_max")
    count_out, _ = await _run("sysctl -n net.netfilter.nf_conntrack_count")
    hash_out, _ = await _run(
        "sysctl -n net.netfilter.nf_conntrack_buckets",
    )

    max_val = _safe_int(max_out)
    count_val = _safe_int(count_out)
    usage_pct = round(count_val / max_val * 100, 1) if max_val > 0 else 0.0

    return {
        "table_size": max_val,
        "current_count": count_val,
        "hash_size": _safe_int(hash_out),
        "usage_percent": usage_pct,
    }


async def set_table_size(size: int) -> dict:
    """Set nf_conntrack_max and persist the value via sysctl.d.

    Args:
        size: The new maximum number of conntrack entries.

    Returns:
        The updated conntrack configuration (same as :func:`get_config`).
    """
    _, rc = await _run(
        f"sysctl -w net.netfilter.nf_conntrack_max={size}",
        sudo=True,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to set nf_conntrack_max to {size}")
    # Persist
    _, rc = await _run(
        f"tee /etc/sysctl.d/91-dawos-conntrack.conf "
        f"<<< 'net.netfilter.nf_conntrack_max = {size}'",
        sudo=True,
    )
    if rc != 0:
        raise RuntimeError("Failed to persist nf_conntrack_max to /etc/sysctl.d")
    return await get_config()


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

_TIMEOUT_KEYS = [
    "net.netfilter.nf_conntrack_tcp_timeout_established",
    "net.netfilter.nf_conntrack_tcp_timeout_close",
    "net.netfilter.nf_conntrack_tcp_timeout_close_wait",
    "net.netfilter.nf_conntrack_tcp_timeout_fin_wait",
    "net.netfilter.nf_conntrack_tcp_timeout_syn_sent",
    "net.netfilter.nf_conntrack_tcp_timeout_syn_recv",
    "net.netfilter.nf_conntrack_tcp_timeout_time_wait",
    "net.netfilter.nf_conntrack_tcp_timeout_last_ack",
    "net.netfilter.nf_conntrack_udp_timeout",
    "net.netfilter.nf_conntrack_udp_timeout_stream",
    "net.netfilter.nf_conntrack_icmp_timeout",
    "net.netfilter.nf_conntrack_generic_timeout",
]


async def get_timeouts() -> dict:
    """Read all nf_conntrack protocol timeout values.

    Returns:
        A dictionary mapping shortened sysctl key names to their
        current timeout values in seconds.
    """
    result: dict[str, int] = {}
    for key in _TIMEOUT_KEYS:
        short = key.replace("net.netfilter.nf_conntrack_", "")
        out, _ = await _run(f"sysctl -n {key}")
        result[short] = _safe_int(out)
    return result


async def set_timeout(key: str, seconds: int) -> dict:
    """Set a single nf_conntrack timeout value.

    Args:
        key: The short timeout key (e.g. ``tcp_timeout_established``).
        seconds: Timeout duration in seconds.

    Returns:
        The updated timeout dictionary (same as :func:`get_timeouts`).

    Raises:
        ValueError: If *key* is not a recognised timeout parameter.
    """
    full_key = f"net.netfilter.nf_conntrack_{key}"
    if full_key not in set(_TIMEOUT_KEYS):
        raise ValueError(f"Unknown timeout key: {key}")
    _, rc = await _run(f"sysctl -w {full_key}={seconds}", sudo=True)
    if rc != 0:
        raise RuntimeError(f"Failed to set {full_key}")
    return await get_timeouts()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def list_helpers() -> list[dict]:
    """List loaded nf_conntrack helper kernel modules.

    Returns:
        A list of dicts with ``module``, ``size``, and ``used_by``
        for each loaded conntrack helper module.
    """
    out, rc = await _run("lsmod")
    if rc != 0:
        return []

    helpers: list[dict] = []
    for line in out.splitlines():
        m = re.match(r"(nf_conntrack_\w+)\s+(\d+)\s+(\d+)", line)
        if m:
            helpers.append(
                {
                    "module": m.group(1),
                    "size": _safe_int(m.group(2)),
                    "used_by": _safe_int(m.group(3)),
                }
            )
    return helpers


# ---------------------------------------------------------------------------
# Profiles — predefined timeout presets for common traffic patterns
# ---------------------------------------------------------------------------

_PROFILES: dict[str, dict[str, int]] = {
    "default": {
        "tcp_timeout_established": 432000,
        "udp_timeout": 30,
        "udp_timeout_stream": 180,
    },
    "gaming": {
        "tcp_timeout_established": 86400,
        "udp_timeout": 60,
        "udp_timeout_stream": 300,
    },
    "streaming": {
        "tcp_timeout_established": 600000,
        "udp_timeout": 60,
        "udp_timeout_stream": 600,
    },
}


def list_profiles() -> list[str]:
    """Return the names of available conntrack tuning profiles.

    Returns:
        A list of profile name strings.
    """
    return list(_PROFILES.keys())


async def apply_profile(name: str) -> dict:
    """Apply a named conntrack tuning profile.

    Each profile sets a predefined combination of TCP and UDP timeout
    values optimised for a specific traffic pattern (e.g. gaming,
    streaming, default).

    Args:
        name: Profile name (must be one of :func:`list_profiles`).

    Returns:
        The updated timeout dictionary (same as :func:`get_timeouts`).

    Raises:
        ValueError: If *name* is not a recognised profile.
    """
    if name not in _PROFILES:
        raise ValueError(f"Unknown profile: {name}")

    for key, val in _PROFILES[name].items():
        _, rc = await _run(
            f"sysctl -w net.netfilter.nf_conntrack_{key}={val}",
            sudo=True,
        )
        if rc != 0:
            raise RuntimeError(f"Failed to apply profile '{name}' at {key}")
    return await get_timeouts()


# ---------------------------------------------------------------------------
# Flush
# ---------------------------------------------------------------------------


async def flush_table() -> dict:
    """Flush all entries from the nf_conntrack table.

    Runs ``conntrack -F`` with sudo to clear every tracked connection.
    Returns the entry count observed *before* the flush for informational
    purposes.

    Returns:
        A dictionary with ``success``, ``message``, and
        ``entries_before``.

    Raises:
        RuntimeError: If the ``conntrack -F`` command fails.
    """
    count_out, _ = await _run("sysctl -n net.netfilter.nf_conntrack_count")
    entries_before = _safe_int(count_out)

    _, rc = await _run("conntrack -F", sudo=True)
    if rc != 0:
        raise RuntimeError("Failed to flush conntrack table")

    return {
        "success": True,
        "message": "Conntrack table flushed",
        "entries_before": entries_before,
    }


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
