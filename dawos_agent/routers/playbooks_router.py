"""Operational playbooks endpoint — pre-defined automation sequences.

Exposes a registry of named playbooks (``health-check``,
``backup-config``, ``safe-restart``) and an execution endpoint that
runs the selected playbook and returns step-by-step results.

Each playbook has a minimum RBAC role requirement:

* ``health-check`` — viewer (read-only diagnostics)
* ``backup-config`` — operator (creates files on disk)
* ``safe-restart`` — admin (restarts the accel-ppp service)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..auth import AdminKey, OperatorKey, ViewerKey
from ..models.schemas import (
    PlaybookInfo,
    PlaybookListResponse,
    PlaybookRunResponse,
    PlaybookStep,
)
from ..services.playbooks import PLAYBOOK_EXECUTORS, PLAYBOOK_REGISTRY

router = APIRouter(prefix="/api/v1", tags=["playbooks"])

#: Maps playbook role requirements to the auth dependencies.
_ROLE_DEPS = {
    "viewer": ViewerKey,
    "operator": OperatorKey,
    "admin": AdminKey,
}


@router.get("/playbooks", response_model=PlaybookListResponse)
async def list_playbooks(_key: str = ViewerKey) -> PlaybookListResponse:
    """List all available operational playbooks.

    Returns metadata for every registered playbook including its name,
    description, and the minimum RBAC role required to execute it.

    Returns:
        PlaybookListResponse: Count and list of playbook metadata.
    """
    playbooks = [PlaybookInfo(**info) for info in PLAYBOOK_REGISTRY.values()]
    return PlaybookListResponse(count=len(playbooks), playbooks=playbooks)


@router.post("/playbooks/{name}/run", response_model=PlaybookRunResponse)
async def run_playbook(name: str, _key: str = AdminKey) -> PlaybookRunResponse:
    """Execute a named playbook and return step-by-step results.

    The playbook runs each step sequentially.  If a critical step
    fails, subsequent steps are skipped and the failure is reported.

    This endpoint requires ``admin`` role access to cover the most
    privileged playbook (``safe-restart``).  Less privileged playbooks
    enforce their own role checks internally.

    Args:
        name: Playbook name (``health-check``, ``backup-config``,
            or ``safe-restart``).

    Returns:
        PlaybookRunResponse: Playbook name, overall success flag,
            and ordered step results.

    Raises:
        HTTPException(404): If the playbook name is not recognised.
    """
    executor = PLAYBOOK_EXECUTORS.get(name)
    if executor is None:
        available = ", ".join(sorted(PLAYBOOK_EXECUTORS.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"Unknown playbook: {name}. Available: {available}",
        )

    steps = await executor()
    step_models = [PlaybookStep(**s) for s in steps]
    all_ok = all(s.success for s in step_models)

    return PlaybookRunResponse(
        playbook=name,
        success=all_ok,
        steps=step_models,
    )
