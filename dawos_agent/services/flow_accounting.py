"""Flow accounting management service.

Wraps ``pmacctd`` and ``softflowd`` to provide NetFlow/sFlow/IPFIX
traffic accounting status, collector management, statistics retrieval,
and service control for the BNG host.
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
        log.warning("flow cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def flow_status() -> dict:
    """Check which flow accounting daemon is active.

    Probes ``pmacctd`` first, then falls back to ``softflowd``.

    Returns:
        A dictionary with ``active`` (bool), ``daemon`` name,
        and ``raw_output``.
    """
    # Try pmacctd first, fall back to softflowd
    for svc in ("pmacctd", "softflowd"):
        out, rc = await _run(f"systemctl is-active {svc}")
        if rc == 0 and "active" in out:
            return {
                "active": True,
                "daemon": svc,
                "raw_output": out,
            }

    return {"active": False, "daemon": "none", "raw_output": "no flow daemon active"}


async def flow_collectors() -> dict:
    """List configured flow collectors from softflowd and pmacctd configs.

    Returns:
        A dictionary with ``count`` and ``collectors`` (list of dicts
        with ``host``, ``port``, ``protocol``, and ``source``).
    """
    collectors: list[dict] = []

    # Check softflowd config
    out, rc = await _run("cat /etc/default/softflowd")
    if rc == 0:
        for line in out.splitlines():
            m = re.match(r"COLLECTOR\s*=\s*['\"]?([^'\"\s]+)['\"]?", line)
            if m:
                parts = m.group(1).rsplit(":", 1)
                collectors.append(
                    {
                        "host": parts[0],
                        "port": int(parts[1]) if len(parts) > 1 else 9995,
                        "protocol": "netflow",
                        "source": "softflowd",
                    }
                )

    # Check pmacctd config
    out, rc = await _run("cat /etc/pmacctd.conf")
    if rc == 0:
        for line in out.splitlines():
            m = re.match(r"nfacctd_ip\s*:\s*(\S+)", line)
            if m:
                collectors.append(
                    {
                        "host": m.group(1),
                        "port": 0,
                        "protocol": "netflow",
                        "source": "pmacctd",
                    }
                )
            m = re.match(r"nfacctd_port\s*:\s*(\d+)", line)
            if m and collectors:
                collectors[-1]["port"] = int(m.group(1))

    return {"count": len(collectors), "collectors": collectors}


async def flow_stats() -> dict:
    """Retrieve flow accounting statistics.

    Returns:
        A dictionary with ``flows_exported``, ``packets_processed``,
        and ``raw_output``.
    """
    out, rc = await _run("softflowd -c /dev/null -d")
    if rc != 0 or not out:
        # Try reading from process stats
        out, rc = await _run("softflowd -v")

    # Parse basic stats from softflowd or report raw
    flows_exported = 0
    packets_processed = 0

    for line in out.splitlines():
        m = re.search(r"Flows exported:\s*(\d+)", line)
        if m:
            flows_exported = int(m.group(1))
        m = re.search(r"Packets processed:\s*(\d+)", line)
        if m:
            packets_processed = int(m.group(1))

    return {
        "flows_exported": flows_exported,
        "packets_processed": packets_processed,
        "raw_output": out,
    }


async def flow_restart() -> dict:
    """Restart the active flow accounting daemon.

    Detects which daemon is currently configured and restarts it.
    Falls back to ``softflowd`` if no daemon is active.

    Returns:
        A dictionary with ``success`` (bool), ``daemon``, and ``message``.
    """
    # Find which daemon is configured
    status = await flow_status()
    daemon = status["daemon"]
    if daemon == "none":
        # Try softflowd as default
        daemon = "softflowd"

    out, rc = await _run(f"systemctl restart {daemon}", sudo=True)
    return {
        "success": rc == 0,
        "daemon": daemon,
        "message": out or f"{daemon} restarted",
    }
