"""Flow accounting management API endpoints.

Provides REST endpoints for monitoring and controlling NetFlow, sFlow,
and IPFIX flow-accounting daemons on the BNG host.  Supports status
queries, collector listing, statistics retrieval, and daemon restarts.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    FlowCollectorsResponse,
    FlowRestartResponse,
    FlowStatsResponse,
    FlowStatusResponse,
)
from ..services import flow_accounting

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/flow", tags=["flow-accounting"])


@router.get("/status", response_model=FlowStatusResponse)
async def flow_status(_key: str = ViewerKey):
    """Retrieve the flow accounting daemon status.

    Checks whether the flow-accounting daemon is running and returns
    its operational state.

    Returns:
        FlowStatusResponse: Active flag and daemon process details.

    Raises:
        HTTPException(500): If the status check fails.
    """
    try:
        data = await flow_accounting.flow_status()
        return FlowStatusResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/collectors", response_model=FlowCollectorsResponse)
async def flow_collectors(_key: str = ViewerKey):
    """List configured flow collectors.

    Returns all flow collector destinations (IP:port pairs) that the
    daemon is currently sending flow records to.

    Returns:
        FlowCollectorsResponse: List of collector endpoints.

    Raises:
        HTTPException(500): If the collector list cannot be retrieved.
    """
    try:
        data = await flow_accounting.flow_collectors()
        return FlowCollectorsResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/stats", response_model=FlowStatsResponse)
async def flow_stats(_key: str = ViewerKey):
    """Retrieve flow accounting statistics.

    Returns counters for exported flows, active flows, and daemon
    uptime information.

    Returns:
        FlowStatsResponse: Flow export and active-flow counters.

    Raises:
        HTTPException(500): If statistics cannot be retrieved.
    """
    try:
        data = await flow_accounting.flow_stats()
        return FlowStatsResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/restart", response_model=FlowRestartResponse)
async def flow_restart(_key: str = ApiKey):
    """Restart the flow accounting daemon.

    Issues a ``systemctl restart`` for the flow-accounting service and
    returns the operation result.

    Returns:
        FlowRestartResponse: Success status and result message.

    Raises:
        HTTPException(500): If the restart operation fails.
    """
    try:
        data = await flow_accounting.flow_restart()
        return FlowRestartResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
