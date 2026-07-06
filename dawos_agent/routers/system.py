"""System information and metrics API endpoints.

Provides REST endpoints for retrieving host-level system information
(hardware, OS, network interfaces) and quick resource-usage metrics
(CPU, memory, disk) from the BNG host.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..auth import ApiKey
from ..models.schemas import MetricsResponse, SystemInfoResponse
from ..services.system import get_metrics, get_system_info

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/info", response_model=SystemInfoResponse)
async def system_info(_key: str = ApiKey):
    """Return full system information.

    Collects hardware details (CPU model, core count, total RAM),
    OS release information, hostname, kernel version, and a list of
    network interfaces with their addresses.

    Returns:
        SystemInfoResponse: Comprehensive host information.
    """
    return get_system_info()


@router.get("/metrics", response_model=MetricsResponse)
async def system_metrics(_key: str = ApiKey):
    """Return a quick resource-usage metrics snapshot.

    Samples current CPU utilisation, memory usage, and disk usage
    for the root filesystem.

    Returns:
        MetricsResponse: CPU, memory, and disk usage percentages.
    """
    return get_metrics()
