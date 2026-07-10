"""DNS forwarding management service.

Wraps ``dnsmasq`` to provide REST management of the local DNS cache
on the BNG host, including upstream server configuration, cache size
tuning, and cache flushing.
"""

from __future__ import annotations

import asyncio
import logging

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


async def status() -> dict:
    """Check the dnsmasq DNS forwarding service status.

    Returns:
        A dictionary with ``running`` (bool), ``backend``, and
        ``upstream_count`` (number of configured upstream servers).
    """
    _out, rc = await _run("systemctl is-active dnsmasq")
    running = rc == 0

    upstream_count = 0
    if running:
        cfg, _ = await _run("grep -c '^server=' /etc/dnsmasq.conf")
        upstream_count = _safe_int(cfg)

    return {
        "running": running,
        "backend": "dnsmasq",
        "upstream_count": upstream_count,
    }


async def get_config() -> dict:
    """Read the current dnsmasq configuration.

    Parses upstream servers, listen address, and cache size from
    ``/etc/dnsmasq.conf``.

    Returns:
        A dictionary with ``servers`` (list), ``listen_address``,
        and ``cache_size``.
    """
    out, rc = await _run("grep '^server=' /etc/dnsmasq.conf")
    servers: list[str] = []
    if rc == 0:
        for line in out.splitlines():
            addr = line.replace("server=", "").strip()
            if addr:
                servers.append(addr)

    listen_out, _ = await _run("grep '^listen-address=' /etc/dnsmasq.conf")
    listen = ""
    if listen_out:
        listen = listen_out.replace("listen-address=", "").strip()

    cache_out, _ = await _run("grep '^cache-size=' /etc/dnsmasq.conf")
    cache = 150  # dnsmasq default
    if cache_out:
        cache = _safe_int(cache_out.replace("cache-size=", "").strip(), 150)

    return {
        "servers": servers,
        "listen_address": listen,
        "cache_size": cache,
    }


async def set_forwarders(servers: list[str], cache_size: int = 1000) -> dict:
    """Write upstream DNS servers to a dnsmasq drop-in config and reload.

    Args:
        servers: List of upstream DNS server addresses.
        cache_size: Maximum number of cached DNS entries (default 1000).

    Returns:
        A dictionary with ``servers`` and ``cache_size`` as confirmed.

    Raises:
        RuntimeError: If dnsmasq is not installed or the reload fails.
    """
    _, rc = await _run("systemctl is-active dnsmasq")
    if rc != 0:
        raise RuntimeError(
            "dnsmasq is not installed or not running — "
            "install with: apt install dnsmasq"
        )

    lines = [f"server={s}" for s in servers]
    lines.append(f"cache-size={cache_size}")
    lines.append("no-resolv")
    conf = "\n".join(lines) + "\n"

    await _run(
        f"tee /etc/dnsmasq.d/dawos-forwarding.conf <<< '{conf}'",
        sudo=True,
    )
    _, rc = await _run("systemctl reload dnsmasq", sudo=True)
    if rc != 0:
        raise RuntimeError("Failed to reload dnsmasq")

    return {"servers": servers, "cache_size": cache_size}


async def flush_cache() -> dict:
    """Flush the dnsmasq DNS cache by sending SIGHUP.

    Returns:
        A dictionary with ``flushed`` (bool).

    Raises:
        RuntimeError: If dnsmasq is not running or signal delivery fails.
    """
    _, rc = await _run("systemctl is-active dnsmasq")
    if rc != 0:
        raise RuntimeError(
            "dnsmasq is not installed or not running — "
            "install with: apt install dnsmasq"
        )

    _, rc = await _run("systemctl kill -s HUP dnsmasq", sudo=True)
    if rc != 0:
        raise RuntimeError("Failed to flush DNS cache")
    return {"flushed": True}


def _safe_int(value: str, default: int = 0) -> int:
    """Convert a string to int, returning *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
