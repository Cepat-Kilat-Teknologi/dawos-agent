"""LLDP neighbor discovery API endpoints.

Provides REST endpoints for querying the Link Layer Discovery Protocol
(LLDP) daemon via ``lldpctl``.  Supports daemon status checks, neighbor
listing, and per-interface neighbor detail retrieval.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path

from ..auth import ViewerKey
from ..constants import RE_SAFE_IFACE
from ..models.schemas import (
    LldpInterfaceResponse,
    LldpNeighborsResponse,
    LldpStatusResponse,
)
from ..services import lldp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lldp", tags=["lldp"])


@router.get("/status", response_model=LldpStatusResponse)
async def lldp_status(_key: str = ViewerKey):
    """Retrieve the LLDP daemon status.

    Checks whether the lldpd process is running and returns its
    operational state.

    Returns:
        LldpStatusResponse: Active flag and daemon details.

    Raises:
        HTTPException(500): If the status check fails.
    """
    try:
        data = await lldp.lldp_status()
        return LldpStatusResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/neighbors", response_model=LldpNeighborsResponse)
async def lldp_neighbors(_key: str = ViewerKey):
    """List all discovered LLDP neighbors.

    Runs ``lldpctl`` and returns every neighbor across all interfaces,
    including chassis ID, port ID, system name, and capabilities.

    Returns:
        LldpNeighborsResponse: List of LLDP neighbor records.

    Raises:
        HTTPException(500): If the neighbor query fails.
    """
    try:
        data = await lldp.lldp_neighbors()
        return LldpNeighborsResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/neighbors/{name}", response_model=LldpInterfaceResponse)
async def lldp_interface(
    name: str = Path(pattern=RE_SAFE_IFACE), _key: str = ViewerKey
):
    """Get LLDP neighbors for a specific interface.

    Returns neighbor information discovered on the named network
    interface only.

    Args:
        name: The network interface name to query.

    Returns:
        LldpInterfaceResponse: Neighbors found on the specified interface.

    Raises:
        HTTPException(500): If the interface query fails.
    """
    try:
        data = await lldp.lldp_interface(name)
        return LldpInterfaceResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
