"""VRRP high-availability API endpoints.

Provides REST endpoints for querying and managing keepalived VRRP
groups on the BNG host.  Supports status checks, group detail
inspection, manual failover triggers, and service restarts.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    VrrpActionResponse,
    VrrpFailoverRequest,
    VrrpGroupDetailResponse,
    VrrpStatusResponse,
)
from ..services import vrrp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vrrp", tags=["vrrp"])


@router.get("/status", response_model=VrrpStatusResponse)
async def vrrp_status(_key: str = ViewerKey):
    """Return VRRP / keepalived status.

    Queries the keepalived daemon and returns the state of all
    configured VRRP instances (MASTER, BACKUP, or FAULT).

    Returns:
        VrrpStatusResponse: Per-instance VRRP state summary.

    Raises:
        HTTPException(500): If the status check fails.
    """
    try:
        data = await vrrp.vrrp_status()
        return VrrpStatusResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/groups/{group}", response_model=VrrpGroupDetailResponse)
async def vrrp_group_detail(group: str, _key: str = ViewerKey):
    """Get detailed information for a specific VRRP group.

    Returns the group's current state, priority, virtual IP addresses,
    advertisement interval, and preemption settings.

    Args:
        group: The VRRP group name (path parameter).

    Returns:
        VrrpGroupDetailResponse: Full group configuration and state.

    Raises:
        HTTPException(500): If the group detail cannot be retrieved.
    """
    try:
        data = await vrrp.vrrp_group_detail(group)
        return VrrpGroupDetailResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/failover", response_model=VrrpActionResponse)
async def vrrp_failover(req: VrrpFailoverRequest, _key: str = ApiKey):
    """Trigger a manual VRRP failover.

    Forces the specified VRRP group to transition to FAULT state,
    causing the backup node to assume MASTER role.

    Args:
        req: Request body with the VRRP group name.

    Returns:
        VrrpActionResponse: Success flag and result message.

    Raises:
        HTTPException(500): If the failover command fails.
    """
    try:
        data = await vrrp.vrrp_failover(req.group)
        return VrrpActionResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/restart", response_model=VrrpActionResponse)
async def vrrp_restart(_key: str = ApiKey):
    """Restart the keepalived service.

    Issues a ``systemctl restart keepalived`` to reload all VRRP
    configuration and re-establish group memberships.

    Returns:
        VrrpActionResponse: Success flag and result message.

    Raises:
        HTTPException(500): If the restart command fails.
    """
    try:
        data = await vrrp.vrrp_restart()
        return VrrpActionResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
