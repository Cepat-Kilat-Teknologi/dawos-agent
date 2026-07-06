"""Health check API endpoint.

Provides a public (no authentication required) liveness probe used by
load balancers, the dawu-radius node-discovery system, and container
orchestrators.  Returns the agent version, node name, and uptime.
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from .. import __version__
from ..config import settings
from ..models.schemas import HealthResponse

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health():
    """Perform a basic health check.

    Always returns HTTP 200 with the node name, agent version, and
    process uptime in seconds.  No authentication is required so that
    external probes can reach this endpoint without credentials.

    Returns:
        HealthResponse: Status ``ok``, node name, version, and uptime.
    """
    return HealthResponse(
        status="ok",
        node_name=settings.node_name,
        version=__version__,
        uptime_seconds=round(time.time() - _start_time, 1),
    )
