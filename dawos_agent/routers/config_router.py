"""accel-ppp configuration file management API endpoints.

Provides REST endpoints for reading, updating, and backing up the
accel-ppp configuration file on the BNG host.  Supports atomic writes
with optional pre-write backups and post-write service restarts.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from ..auth import AdminKey, ViewerKey
from ..config import settings
from ..models.schemas import (
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
    ConfigValidationRequest,
    ConfigValidationResponse,
)
from ..services import config_manager, config_validator

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_config(_key: str = ViewerKey):
    """Read the current accel-ppp configuration file.

    Returns the full text content of the configuration file along with
    its filesystem path and last-modified timestamp.

    Returns:
        ConfigResponse: File path, content, and last-modified timestamp.

    Raises:
        HTTPException(404): If the configuration file does not exist.
        HTTPException(500): If the file cannot be read.
    """
    try:
        content, mtime = config_manager.read_config()
        return ConfigResponse(
            path=str(settings.accel_config_path),
            content=content,
            last_modified=mtime,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("", response_model=ConfigUpdateResponse)
async def update_config(req: ConfigUpdateRequest, _key: str = AdminKey):
    """Update the accel-ppp configuration file.

    Writes the provided content to the configuration file.  Optionally
    creates a timestamped backup before writing and restarts the
    accel-ppp systemd service after the write completes.

    Args:
        req: Request body containing new config content, backup flag,
            and restart flag.

    Returns:
        ConfigUpdateResponse: Success status, message, and backup path.

    Raises:
        HTTPException(500): If the write or service restart fails.
    """
    try:
        backup_path = config_manager.write_config(req.content, backup=req.backup)

        if req.restart_service:
            svc = settings.accel_service_name
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "systemctl",
                "restart",
                svc,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip()
                return ConfigUpdateResponse(
                    success=False,
                    message=f"Config saved but restart failed: {err}",
                    backup_path=backup_path,
                )

        msg = "Config updated"
        if req.restart_service:
            msg += " and service restarted"

        return ConfigUpdateResponse(success=True, message=msg, backup_path=backup_path)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/backups")
async def list_backups(_key: str = ViewerKey):
    """List available configuration backups.

    Returns a list of all ``.bak`` and ``.checkpoint`` files in the
    backup directory, sorted by creation time.

    Returns:
        list[dict]: Backup file metadata including name, size, and
            creation timestamp.
    """
    return config_manager.list_backups()


@router.post("/validate", response_model=ConfigValidationResponse)
async def validate_config(req: ConfigValidationRequest, _key: str = ViewerKey):
    """Validate accel-ppp configuration content without applying it.

    Performs structural and semantic checks on the provided configuration
    text: syntax validation, required section verification, IP/CIDR
    checks, port range validation, and duplicate section detection.

    This is a read-only operation — the configuration file on disk is
    not modified.

    Args:
        req: Request body containing the configuration text to validate.

    Returns:
        ConfigValidationResponse: Validation results with issues list.

    Raises:
        HTTPException(500): If the validation logic itself fails.
    """
    try:
        result = config_validator.validate_config(req.content)
        return ConfigValidationResponse(**result)
    except Exception as exc:
        log.error("Config validation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
