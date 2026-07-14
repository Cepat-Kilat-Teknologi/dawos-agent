"""RADIUS diagnostics API endpoints.

Provides read-only endpoints for inspecting RADIUS configuration,
runtime status, and server reachability on the BNG host.

**Security:** shared secrets are **never** returned by any endpoint.
The ``GET /radius/config`` endpoint strips secrets from server lines
before constructing the response.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ViewerKey
from ..models.schemas import (
    RadiusCheckResponse,
    RadiusConfigResponse,
    RadiusStatusResponse,
)
from ..services import radius

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/radius", tags=["radius"])


@router.get("/config", response_model=RadiusConfigResponse)
async def radius_config(_key: str = ViewerKey):
    """Return the RADIUS configuration from ``accel-ppp.conf``.

    Parses the ``[radius]`` section of the accel-ppp configuration
    file and returns server addresses, ports, NAS identity, and
    timeout settings.  **Shared secrets are never included.**

    Returns:
        RadiusConfigResponse: Parsed RADIUS configuration.

    Raises:
        HTTPException(500): If the config file cannot be read.
    """
    try:
        data = await radius.read_radius_config()
        return RadiusConfigResponse(**data)
    except Exception as exc:
        log.error("Failed to read RADIUS config: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/status", response_model=RadiusStatusResponse)
async def radius_status(_key: str = ViewerKey):
    """Return live RADIUS server statistics from ``accel-cmd show stat``.

    Queries the running accel-ppp daemon for per-server RADIUS metrics
    including authentication, accounting, and interim counters with
    sent/lost/latency breakdowns.

    Returns:
        RadiusStatusResponse: Per-server runtime statistics and summary.

    Raises:
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        data = await radius.get_radius_status()
        return RadiusStatusResponse(**data)
    except Exception as exc:
        log.error("Failed to get RADIUS status: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/check", response_model=RadiusCheckResponse)
async def radius_check(_key: str = ViewerKey):
    """Run a RADIUS server diagnostic check.

    For every RADIUS server configured in ``accel-ppp.conf``:

    1. Tests TCP reachability to the authentication port.
    2. Queries accel-ppp for the server's runtime state.

    The ``healthy`` flag is ``True`` only when **all** configured
    servers are both reachable and in ``active`` state.

    Returns:
        RadiusCheckResponse: Per-server check results and overall verdict.

    Raises:
        HTTPException(500): If the diagnostic check itself fails.
    """
    try:
        data = await radius.check_radius()
        return RadiusCheckResponse(**data)
    except Exception as exc:
        log.error("RADIUS check failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
