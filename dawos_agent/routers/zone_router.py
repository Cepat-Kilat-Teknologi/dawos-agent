"""Zone-based firewall API endpoints.

Provides REST endpoints for managing nftables zone-based firewall
policies on the BNG host.  Supports listing zones, inspecting zone
details and rules, creating new zones with interface bindings, and
deleting zones.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    CreateZoneRequest,
    ZoneActionResponse,
    ZoneDetailResponse,
    ZoneListResponse,
)
from ..services import zone_firewall

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zones", tags=["zone-firewall"])


@router.get("", response_model=ZoneListResponse)
async def list_zones(_key: str = ViewerKey):
    """List all firewall zones.

    Returns every configured zone with its name, bound interfaces,
    and default policy.

    Returns:
        ZoneListResponse: Count and list of zone records.

    Raises:
        HTTPException(500): If the zone listing fails.
    """
    try:
        data = await zone_firewall.list_zones()
        return ZoneListResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/{zone}", response_model=ZoneDetailResponse)
async def zone_detail(zone: str, _key: str = ViewerKey):
    """Get detailed information and rules for a firewall zone.

    Returns the zone's bound interfaces, default policy, and all
    associated nftables rules.

    Args:
        zone: The zone name to inspect (path parameter).

    Returns:
        ZoneDetailResponse: Zone configuration and rule list.

    Raises:
        HTTPException(500): If the zone detail cannot be retrieved.
    """
    try:
        data = await zone_firewall.zone_detail(zone)
        return ZoneDetailResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("", status_code=201, response_model=ZoneActionResponse)
async def create_zone(req: CreateZoneRequest, _key: str = ApiKey):
    """Create a new firewall zone.

    Creates a zone with the given name and optionally binds it to
    the specified network interfaces.

    Args:
        req: Request body with zone name and optional interface list.

    Returns:
        ZoneActionResponse: Success flag and result message.

    Raises:
        HTTPException(500): If the zone cannot be created.
    """
    try:
        data = await zone_firewall.create_zone(req.name, interfaces=req.interfaces)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    if not data.get("success"):
        raise HTTPException(
            status_code=409, detail=data.get("message", "Zone creation failed")
        )
    return ZoneActionResponse(**data)


@router.delete("/{zone}", status_code=204)
async def delete_zone(zone: str, _key: str = ApiKey):
    """Delete a firewall zone.

    Removes the named zone and unbinds all associated interfaces.

    Args:
        zone: The zone name to delete (path parameter).

    Raises:
        HTTPException(500): If the zone cannot be deleted.
    """
    try:
        data = await zone_firewall.delete_zone(zone)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    if not data.get("success"):
        raise HTTPException(
            status_code=404, detail=data.get("message", f"Zone '{zone}' not found")
        )
