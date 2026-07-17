"""Monitoring exporter management service.

Wraps ``node_exporter`` (Prometheus) and ``snmpd`` (SNMP) to provide
status checks, metrics retrieval, and service control for the BNG
host's monitoring infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex

from ..constants import NODE_EXPORTER_PORT, SNMPD_PORT

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
        log.warning("mon cmd failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def monitoring_status() -> dict:
    """Return the status of all monitoring exporters.

    Checks ``node_exporter`` (port 9100) and ``snmpd`` (port 161).

    Returns:
        A dictionary with ``exporters`` (list of dicts with ``service``,
        ``active``, ``port``) and ``count``.
    """
    exporters: list[dict] = []

    for svc, port in [("node_exporter", NODE_EXPORTER_PORT), ("snmpd", SNMPD_PORT)]:
        out, rc = await _run(f"systemctl is-active {svc}")
        active = rc == 0 and "active" in out
        exporters.append(
            {
                "service": svc,
                "active": active,
                "port": port,
            }
        )

    return {
        "exporters": exporters,
        "count": len(exporters),
    }


async def exporter_metrics(service: str = "node_exporter") -> dict:
    """Retrieve basic metrics from a running exporter.

    For ``node_exporter``, fetches the first 50 lines from the
    ``/metrics`` HTTP endpoint.  For ``snmpd``, checks whether
    UDP port 161 is listening.

    Args:
        service: Exporter service name (default ``node_exporter``).

    Returns:
        A dictionary with ``service``, ``available`` (bool),
        ``metrics`` (list of name/value dicts), and ``raw_output``.
    """
    port_map = {"node_exporter": NODE_EXPORTER_PORT, "snmpd": SNMPD_PORT}
    port = port_map.get(service, NODE_EXPORTER_PORT)

    if service == "node_exporter":
        out, rc = await _run(f"curl -sf http://localhost:{port}/metrics")
        if rc != 0:
            return {
                "service": service,
                "available": False,
                "metrics": [],
                "raw_output": out,
            }

        # Truncate to first 50 lines (replaces shell ``| head -50``).
        lines = out.splitlines()[:50]
        truncated = "\n".join(lines)

        metrics: list[dict] = []
        for line in lines:
            if line.startswith("#"):
                continue
            m = re.match(r"(\S+?)(?:\{[^}]*\})?\s+([\d.eE+-]+)", line)
            if m:
                metrics.append({"name": m.group(1), "value": m.group(2)})

        return {
            "service": service,
            "available": True,
            "metrics": metrics,
            "raw_output": truncated,
        }

    # SNMP — just check if listening
    out, rc = await _run("ss -lnup")
    # Filter for the SNMP port in Python instead of piping to grep.
    if rc == 0:
        rc = 0 if f":{SNMPD_PORT}" in out else 1
    return {
        "service": service,
        "available": rc == 0,
        "metrics": [],
        "raw_output": out,
    }


async def configure_exporter(service: str, *, enable: bool = True) -> dict:
    """Enable or disable a monitoring exporter via systemd.

    Args:
        service: The exporter service name.
        enable: If True, enable and start; if False, disable and stop.

    Returns:
        A dictionary with ``success``, ``service``, ``enabled``,
        and ``message``.
    """
    action = "enable --now" if enable else "disable --now"
    out, rc = await _run(f"systemctl {action} {shlex.quote(service)}", sudo=True)
    return {
        "success": rc == 0,
        "service": service,
        "enabled": enable,
        "message": out or f"{service} {'enabled' if enable else 'disabled'}",
    }


async def exporter_restart(service: str) -> dict:
    """Restart a monitoring exporter via systemd.

    Args:
        service: The exporter service name to restart.

    Returns:
        A dictionary with ``success`` (bool), ``service``, and ``message``.
    """
    out, rc = await _run(f"systemctl restart {shlex.quote(service)}", sudo=True)
    return {
        "success": rc == 0,
        "service": service,
        "message": out or f"{service} restarted",
    }
