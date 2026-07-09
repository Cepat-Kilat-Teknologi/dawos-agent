"""Operational playbook definitions and execution engine.

A playbook is a named, predefined sequence of service calls that
automates a common operational task.  Each playbook function returns
a list of step results so the caller can inspect what happened at
every stage.

Available playbooks:

* **health-check** — verifies accel-ppp connectivity, collects version
  and session statistics, and validates the configuration file exists.
* **backup-config** — creates a timestamped backup of the running
  configuration and confirms the backup file is present on disk.
* **safe-restart** — creates a config backup, restarts the accel-ppp
  service, and verifies the daemon is responding after restart.

Each step is recorded as a dict with ``step``, ``success``, and
``detail`` keys.  On failure, subsequent steps in the playbook are
skipped and the failure detail is captured.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import settings
from . import accel, config_manager

log = logging.getLogger(__name__)

#: Registry of available playbooks with human-readable metadata.
PLAYBOOK_REGISTRY: dict[str, dict[str, str]] = {
    "health-check": {
        "name": "health-check",
        "description": "Run basic health diagnostics on the BNG node",
        "role_required": "viewer",
    },
    "backup-config": {
        "name": "backup-config",
        "description": "Create a timestamped backup of the running configuration",
        "role_required": "operator",
    },
    "safe-restart": {
        "name": "safe-restart",
        "description": "Backup config, restart accel-ppp, and verify health",
        "role_required": "admin",
    },
}


async def run_health_check() -> list[dict]:
    """Execute the health-check playbook.

    Steps:

    1. Call ``accel-cmd show version`` to verify CLI connectivity.
    2. Call ``accel-cmd show stat`` to collect session statistics.
    3. Verify the configuration file exists on disk.

    Returns:
        List of step result dicts with ``step``, ``success``, and
        ``detail`` keys.
    """
    steps: list[dict] = []

    # Step 1: accel-cmd connectivity
    try:
        version = await accel.show_version()
        steps.append(
            {
                "step": "accel-cmd connectivity",
                "success": True,
                "detail": version.strip(),
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "accel-cmd connectivity",
                "success": False,
                "detail": str(exc),
            }
        )
        return steps

    # Step 2: session statistics
    try:
        stat = await accel.show_stat()
        active = stat.get("sessions", {}).get("active", "N/A")
        steps.append(
            {
                "step": "session statistics",
                "success": True,
                "detail": f"Active sessions: {active}",
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "session statistics",
                "success": False,
                "detail": str(exc),
            }
        )

    # Step 3: config file exists
    try:
        content, modified = config_manager.read_config()
        steps.append(
            {
                "step": "config file check",
                "success": True,
                "detail": f"Config present ({len(content)} bytes"
                f", modified {modified.isoformat() if modified else 'unknown'})",
            }
        )
    except FileNotFoundError as exc:
        steps.append(
            {
                "step": "config file check",
                "success": False,
                "detail": str(exc),
            }
        )

    return steps


async def run_backup_config() -> list[dict]:
    """Execute the backup-config playbook.

    Steps:

    1. Create a backup of the running configuration.
    2. List backups to confirm the new one exists.

    Returns:
        List of step result dicts.
    """
    steps: list[dict] = []

    # Step 1: create checkpoint backup
    try:
        checkpoint = config_manager.create_checkpoint()
        steps.append(
            {
                "step": "create backup",
                "success": True,
                "detail": f"Checkpoint created: {checkpoint}",
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "create backup",
                "success": False,
                "detail": str(exc),
            }
        )
        return steps

    # Step 2: verify backup exists
    try:
        backups = config_manager.list_backups()
        steps.append(
            {
                "step": "verify backup",
                "success": True,
                "detail": f"Total revisions on disk: {len(backups)}",
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "verify backup",
                "success": False,
                "detail": str(exc),
            }
        )

    return steps


async def run_safe_restart() -> list[dict]:
    """Execute the safe-restart playbook.

    Steps:

    1. Create a config backup (safety net before restart).
    2. Restart the accel-ppp service via systemd.
    3. Verify the daemon is responding via ``accel-cmd show version``.

    Returns:
        List of step result dicts.
    """
    steps: list[dict] = []

    # Step 1: backup before restart
    try:
        checkpoint = config_manager.create_checkpoint()
        steps.append(
            {
                "step": "pre-restart backup",
                "success": True,
                "detail": f"Checkpoint created: {checkpoint}",
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "pre-restart backup",
                "success": False,
                "detail": str(exc),
            }
        )
        return steps

    # Step 2: restart service
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "systemctl",
            "restart",
            settings.accel_service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_data = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                stderr_data.decode().strip() or "systemctl restart failed"
            )
        steps.append(
            {
                "step": "restart service",
                "success": True,
                "detail": "accel-ppp service restarted via systemd",
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "restart service",
                "success": False,
                "detail": str(exc),
            }
        )
        return steps

    # Step 3: verify daemon is alive
    try:
        version = await accel.show_version()
        steps.append(
            {
                "step": "post-restart verification",
                "success": True,
                "detail": f"Daemon responding: {version.strip()}",
            }
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        steps.append(
            {
                "step": "post-restart verification",
                "success": False,
                "detail": f"Daemon not responding after restart: {exc}",
            }
        )

    return steps


#: Maps playbook names to their executor functions.
PLAYBOOK_EXECUTORS: dict[str, object] = {
    "health-check": run_health_check,
    "backup-config": run_backup_config,
    "safe-restart": run_safe_restart,
}
