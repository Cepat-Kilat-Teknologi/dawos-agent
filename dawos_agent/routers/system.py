"""System information and metrics API endpoints.

Provides REST endpoints for retrieving host-level system information
(hardware, OS, network interfaces) and quick resource-usage metrics
(CPU, memory, disk) from the BNG host.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ViewerKey
from ..models.schemas import ExtendedStatsResponse, MetricsResponse, SystemInfoResponse
from ..services import accel
from ..services.system import get_metrics, get_system_info

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/info", response_model=SystemInfoResponse)
async def system_info(_key: str = ViewerKey):
    """Return full system information.

    Collects hardware details (CPU model, core count, total RAM),
    OS release information, hostname, kernel version, and a list of
    network interfaces with their addresses.

    Returns:
        SystemInfoResponse: Comprehensive host information.
    """
    return get_system_info()


@router.get("/metrics", response_model=MetricsResponse)
async def system_metrics(_key: str = ViewerKey):
    """Return a quick resource-usage metrics snapshot.

    Samples current CPU utilisation, memory usage, and disk usage
    for the root filesystem.

    Returns:
        MetricsResponse: CPU, memory, and disk usage percentages.
    """
    return get_metrics()


@router.get("/stats", response_model=ExtendedStatsResponse)
async def system_stats(_key: str = ViewerKey):
    """Return comprehensive accel-ppp runtime statistics.

    Parses every section of ``accel-cmd show stat`` output including
    uptime, CPU, memory (RSS/virtual), core subsystem counters,
    session counts, PPPoE protocol counters, and per-RADIUS-server
    statistics (auth/acct/interim sent/lost/latency).

    This is the extended counterpart to ``GET /api/v1/sessions/stats``
    which only returns a summary.

    Returns:
        ExtendedStatsResponse: Full accel-ppp runtime statistics.
    """
    try:
        data = await accel.show_stat_extended()
    except RuntimeError as exc:
        log.exception("Failed to retrieve extended stats")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    return ExtendedStatsResponse(**data)
