"""Dynamic routing protocol API endpoints.

Provides REST endpoints for querying BGP, OSPF, RIP, and BFD status
from the FRRouting (FRR) suite via ``vtysh`` on the BNG host.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey
from ..models.schemas import (
    BfdPeersResponse,
    BfdSummaryResponse,
    BgpRoutesResponse,
    BgpStatusResponse,
    OspfRoutesResponse,
    OspfStatusResponse,
    RipRoutesResponse,
    RipStatusResponse,
)
from ..services import routing

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/routing", tags=["routing"])


# ---------------------------------------------------------------------------
# BGP
# ---------------------------------------------------------------------------


@router.get("/bgp/status", response_model=BgpStatusResponse)
async def bgp_status(_key: str = ApiKey):
    """Return the BGP summary.

    Queries ``vtysh -c 'show bgp summary json'`` and returns the
    router ID, local AS number, neighbor states, and prefix counts.

    Returns:
        BgpStatusResponse: BGP summary with neighbor details.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.bgp_summary()
        return BgpStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/bgp/routes", response_model=BgpRoutesResponse)
async def bgp_routes(_key: str = ApiKey):
    """Return BGP IPv4 unicast routes.

    Queries the FRR RIB for all BGP-learned IPv4 unicast prefixes.

    Returns:
        BgpRoutesResponse: List of BGP route entries.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.bgp_routes()
        return BgpRoutesResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# OSPF
# ---------------------------------------------------------------------------


@router.get("/ospf/status", response_model=OspfStatusResponse)
async def ospf_status(_key: str = ApiKey):
    """Return OSPF status.

    Queries ``vtysh -c 'show ip ospf json'`` and returns the router
    ID, areas, SPF run count, and configuration state.

    Returns:
        OspfStatusResponse: OSPF router status and area summary.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.ospf_status()
        return OspfStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ospf/neighbors", response_model=OspfStatusResponse)
async def ospf_neighbors(_key: str = ApiKey):
    """Return the OSPF neighbor table.

    Lists all OSPF adjacencies with neighbor ID, state, dead timer,
    and the interface each adjacency is formed on.

    Returns:
        OspfStatusResponse: OSPF neighbor list.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.ospf_neighbors()
        return OspfStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ospf/routes", response_model=OspfRoutesResponse)
async def ospf_routes(_key: str = ApiKey):
    """Return OSPF routes from the routing table.

    Queries the FRR RIB for all OSPF-learned routes including intra-area,
    inter-area, and external routes.

    Returns:
        OspfRoutesResponse: List of OSPF route entries.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.ospf_routes()
        return OspfRoutesResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# RIP
# ---------------------------------------------------------------------------


@router.get("/rip/status", response_model=RipStatusResponse)
async def rip_status(_key: str = ApiKey):
    """Return RIP protocol status.

    Queries ``vtysh`` for the RIP version, configured networks,
    neighbor list, and redistribution settings.

    Returns:
        RipStatusResponse: RIP configuration and neighbor summary.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.rip_status()
        return RipStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/rip/routes", response_model=RipRoutesResponse)
async def rip_routes(_key: str = ApiKey):
    """Return RIP routing table entries.

    Lists all routes learned via the RIP protocol with their metric,
    next-hop, and age.

    Returns:
        RipRoutesResponse: List of RIP route entries.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.rip_routes()
        return RipRoutesResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# BFD
# ---------------------------------------------------------------------------


@router.get("/bfd/peers", response_model=BfdPeersResponse)
async def bfd_peers(_key: str = ApiKey):
    """Return BFD peer status.

    Lists all Bidirectional Forwarding Detection peers with their
    session state, local/remote discriminator, and timers.

    Returns:
        BfdPeersResponse: List of BFD peer records.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.bfd_peers()
        return BfdPeersResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/bfd/summary", response_model=BfdSummaryResponse)
async def bfd_summary(_key: str = ApiKey):
    """Return BFD counters summary.

    Provides aggregate BFD statistics including total peers, sessions
    up/down, and control-packet counters.

    Returns:
        BfdSummaryResponse: BFD aggregate counters.

    Raises:
        HTTPException(500): If the vtysh command fails.
    """
    try:
        data = await routing.bfd_summary()
        return BfdSummaryResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
