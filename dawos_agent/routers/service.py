"""accel-ppp service management API endpoints.

Provides REST endpoints for controlling the accel-ppp systemd service
(start, stop, restart, reload) and executing whitelisted ``accel-cmd``
commands on the BNG host.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, HTTPException

from ..auth import AdminKey, ViewerKey
from ..config import settings
from ..models.schemas import (
    CommandRequest,
    CommandResponse,
    ServiceAction,
    ServiceActionResponse,
    ServiceStatus,
    ServiceStatusResponse,
)
from ..services import accel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/service", tags=["service"])

# Commands allowed through the command endpoint (whitelist approach)
_ALLOWED_COMMANDS = {
    "show stat",
    "show sessions",
    "show ippool",
    "show version",
    "reload",
}


def _is_allowed_command(cmd: str) -> bool:
    """Check if a command is in the whitelist or matches safe patterns.

    Validates the given accel-cmd command against an explicit
    whitelist and a set of safe prefix patterns.  This prevents
    arbitrary command execution through the ``/command`` endpoint.

    Args:
        cmd: The raw command string to validate.

    Returns:
        True if the command is allowed, False otherwise.
    """
    cmd = cmd.strip()
    if cmd in _ALLOWED_COMMANDS:
        return True
    # Allow 'show sessions' with column specifiers
    if cmd.startswith("show sessions "):
        return True
    # Allow 'terminate' commands
    if cmd.startswith("terminate "):
        return True
    # Allow 'shaper' commands
    if cmd.startswith("shaper "):
        return True
    # Allow 'pppoe mac-filter' commands
    return bool(cmd.startswith("pppoe mac-filter "))


@router.get("/status", response_model=ServiceStatusResponse)
async def service_status(_key: str = ViewerKey):
    """Check accel-ppp service status.

    Queries ``systemctl`` for the accel-ppp unit's active state, PID,
    uptime, and version.  Returns ``unknown`` status if the check
    itself fails.

    Returns:
        ServiceStatusResponse: Service name, status, PID, uptime,
            and version.
    """
    svc = settings.accel_service_name
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-active",
            svc,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        state = stdout.decode().strip()

        status = ServiceStatus.running if state == "active" else ServiceStatus.stopped

        # Get PID if running
        pid = None
        version = None
        uptime = None
        if status == ServiceStatus.running:
            try:
                proc2 = await asyncio.create_subprocess_exec(
                    "systemctl",
                    "show",
                    svc,
                    "--property=MainPID",
                    stdout=asyncio.subprocess.PIPE,
                )
                out2, _ = await proc2.communicate()
                pid_str = out2.decode().strip().split("=", 1)[-1]
                pid = int(pid_str) if pid_str.isdigit() and pid_str != "0" else None
            except Exception:
                pass

            with contextlib.suppress(Exception):
                version = await accel.show_version()

            try:
                stat = await accel.show_stat()
                uptime = stat.get("uptime", "")
            except Exception:
                pass

        return ServiceStatusResponse(
            name=svc,
            status=status,
            pid=pid,
            uptime=uptime,
            version=version,
        )
    except Exception as exc:
        log.error("Failed to check service status: %s", exc)
        return ServiceStatusResponse(name=svc, status=ServiceStatus.unknown)


@router.post("/command", response_model=CommandResponse)
async def run_command(req: CommandRequest, _key: str = AdminKey):
    """Execute a whitelisted accel-cmd command.

    Validates the command against the built-in whitelist before
    execution.  Only safe, read-only, and session-management
    commands are allowed.

    Args:
        req: Request body with the accel-cmd command string.

    Returns:
        CommandResponse: Success flag, command output, and the
            command that was run.

    Raises:
        HTTPException(403): If the command is not whitelisted.
    """
    if not _is_allowed_command(req.command):
        raise HTTPException(
            status_code=403,
            detail=f"Command not allowed: {req.command}",
        )

    try:
        output = await accel.run_cmd(req.command)
        return CommandResponse(success=True, output=output, command=req.command)
    except Exception as exc:
        return CommandResponse(success=False, output=str(exc), command=req.command)


@router.post("/{action}", response_model=ServiceActionResponse)
async def service_action(action: ServiceAction, _key: str = AdminKey):
    """Start, stop, restart, or reload accel-ppp.

    For ``reload``, uses ``accel-cmd reload`` which is graceful and
    does not drop active sessions.  For ``start``, ``stop``, and
    ``restart``, issues the corresponding ``systemctl`` command.

    Args:
        action: The service action to perform (start/stop/restart/reload).

    Returns:
        ServiceActionResponse: Action performed, success flag, and message.

    Raises:
        HTTPException(500): If the systemctl or reload command fails.
    """
    svc = settings.accel_service_name

    if action == ServiceAction.reload:
        # Use accel-cmd reload (graceful, no session drop)
        try:
            await accel.reload_config()
            return ServiceActionResponse(
                action=action, success=True, message="Config reloaded"
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # systemctl start/stop/restart
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "systemctl",
            action.value,
            svc,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise HTTPException(
                status_code=500, detail=f"systemctl {action.value} failed: {err}"
            )

        return ServiceActionResponse(
            action=action,
            success=True,
            message=f"Service {action.value} successful",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
