"""Config checkpoint endpoints — diff, rollback, guarded apply with auto-rollback.

dawos-agent checkpoint pattern:
    1. ``POST /apply``   — write new config + start auto-rollback timer
    2. Operator verifies the BNG still works
    3. ``POST /confirm`` — cancel timer, keep new config
    4. If no confirm within deadline → auto-rollback to checkpoint

This is intentionally simpler than commit-tree systems: no revision
numbering, no gzip archives, no external timer daemons.  Just asyncio
tasks and timestamped ``.bak`` / ``.checkpoint`` files.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import AdminKey, ViewerKey
from ..models.schemas import (
    CheckpointDiffResponse,
    CheckpointListResponse,
    CheckpointRevision,
    CheckpointRollbackResponse,
    ConfirmApplyResponse,
    GuardedApplyRequest,
    GuardedApplyResponse,
    GuardedStatusResponse,
    RevisionCompareResponse,
    RevisionContentResponse,
)
from ..services import config_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["checkpoint"])


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


@router.get("/revisions", response_model=CheckpointListResponse)
async def list_revisions(_key: str = ViewerKey):
    """List all configuration backup and checkpoint revisions.

    Scans the backup directory for ``.bak`` and ``.checkpoint`` files and
    returns them sorted by creation time.

    Returns:
        CheckpointListResponse: Count and list of available revisions.
    """
    backups = config_manager.list_backups()
    revisions = [
        CheckpointRevision(
            name=b["name"],
            size=b["size"],
            created=b["created"],
            is_checkpoint=b["name"].endswith(".checkpoint"),
        )
        for b in backups
    ]
    return CheckpointListResponse(count=len(revisions), revisions=revisions)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@router.get("/diff", response_model=CheckpointDiffResponse)
async def diff_revision(backup_name: str, _key: str = ViewerKey):
    """Compute a unified diff between the running config and a backup.

    Compares the current ``accel-ppp.conf`` against the specified backup
    or checkpoint file and returns the unified-diff output.

    Args:
        backup_name: Filename of the backup to diff against.

    Returns:
        CheckpointDiffResponse: Unified diff output with change summary.

    Raises:
        HTTPException(404): If the named backup file does not exist.
        HTTPException(500): If the diff operation fails unexpectedly.
    """
    try:
        result = config_manager.diff_with_backup(backup_name)
        return CheckpointDiffResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


@router.post("/rollback/{backup_name}", response_model=CheckpointRollbackResponse)
async def rollback(backup_name: str, _key: str = AdminKey):
    """Restore a previous configuration revision.

    Creates a safety backup of the current running config before
    overwriting it with the contents of the specified backup file.

    Args:
        backup_name: Filename of the backup to restore.

    Returns:
        CheckpointRollbackResponse: Success status and safety backup path.

    Raises:
        HTTPException(404): If the named backup file does not exist.
        HTTPException(500): If the rollback operation fails unexpectedly.
    """
    try:
        safety = config_manager.rollback_to(backup_name)
        return CheckpointRollbackResponse(
            success=True,
            message=f"Config rolled back from {backup_name}",
            safety_backup=safety,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Revision content
# ---------------------------------------------------------------------------


@router.get("/revisions/{name}/content", response_model=RevisionContentResponse)
async def revision_content(name: str, _key: str = ViewerKey):
    """Read the full content of a specific configuration revision.

    Returns the text content, file size, and creation timestamp of
    the named backup or checkpoint file.

    Args:
        name: Filename of the revision to read.

    Returns:
        RevisionContentResponse: Revision content and metadata.

    Raises:
        HTTPException(404): If the named revision does not exist.
    """
    try:
        content, size, created = config_manager.read_backup(name)
        return RevisionContentResponse(
            name=name,
            size=size,
            created=created,
            content=content,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Compare two revisions
# ---------------------------------------------------------------------------


@router.get("/compare", response_model=RevisionCompareResponse)
async def compare_revisions(
    from_name: str,
    to_name: str,
    _key: str = ViewerKey,
):
    """Compute a unified diff between two named configuration revisions.

    Unlike the ``/diff`` endpoint which compares a revision against the
    running config, this endpoint compares any two historical revisions
    directly.

    Args:
        from_name: Filename of the first (older) revision.
        to_name: Filename of the second (newer) revision.

    Returns:
        RevisionCompareResponse: Unified diff output with change flag.

    Raises:
        HTTPException(404): If either revision does not exist.
    """
    try:
        result = config_manager.diff_two_revisions(from_name, to_name)
        return RevisionCompareResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Guarded apply
# ---------------------------------------------------------------------------


@router.post("/apply", response_model=GuardedApplyResponse)
async def guarded_apply(req: GuardedApplyRequest, _key: str = AdminKey):
    """Apply new config with auto-rollback timer.

    The operator must call ``POST /confirm`` within *confirm_minutes*
    or the config will automatically revert to the checkpoint.
    """
    try:
        # 1. Create checkpoint of current config
        cp = config_manager.create_checkpoint()

        # 2. Write new config (with standard backup)
        config_manager.write_config(req.content, backup=True)

        # 3. Start auto-rollback timer
        deadline_seconds = req.confirm_minutes * 60
        config_manager.start_guarded_timer(deadline_seconds)

        return GuardedApplyResponse(
            success=True,
            message=f"Config applied — confirm within {req.confirm_minutes}m or auto-rollback",
            checkpoint=cp or "",
            confirm_deadline_seconds=deadline_seconds,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/confirm", response_model=ConfirmApplyResponse)
async def confirm_apply(_key: str = AdminKey):
    """Confirm a pending guarded apply and cancel the auto-rollback timer.

    Must be called within the deadline window set during ``POST /apply``.
    If no guarded apply is pending, returns HTTP 409.

    Returns:
        ConfirmApplyResponse: Confirmation acknowledgement.

    Raises:
        HTTPException(409): If there is no pending guarded apply to confirm.
    """
    status = config_manager.guarded_apply_status()
    if not status["pending"]:
        raise HTTPException(status_code=409, detail="No pending apply to confirm")

    config_manager.cancel_guarded_timer()
    return ConfirmApplyResponse(
        success=True,
        message="Config confirmed — auto-rollback cancelled",
    )


@router.get("/apply/status", response_model=GuardedStatusResponse)
async def apply_status(_key: str = ViewerKey):
    """Check whether a guarded apply is pending confirmation.

    Returns the current timer state including whether an apply is
    pending, the remaining deadline, and the checkpoint filename.

    Returns:
        GuardedStatusResponse: Pending flag, deadline, and checkpoint info.
    """
    status = config_manager.guarded_apply_status()
    return GuardedStatusResponse(**status)
