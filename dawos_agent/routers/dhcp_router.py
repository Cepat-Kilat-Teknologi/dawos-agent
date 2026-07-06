"""DHCP management API endpoints.

Provides REST endpoints for monitoring and controlling DHCP server
and relay services on the BNG host.  Supports status queries, lease
inspection, and service restart operations.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey
from ..models.schemas import (
    DhcpActionResponse,
    DhcpLeasesResponse,
    DhcpRelayStatusResponse,
    DhcpStatusResponse,
)
from ..services import dhcp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dhcp", tags=["dhcp"])


@router.get("/status", response_model=DhcpStatusResponse)
async def dhcp_status(_key: str = ApiKey):
    """Retrieve the current DHCP server status.

    Checks whether the ISC DHCP server process is active and returns
    its operational state.

    Returns:
        DhcpStatusResponse: Current DHCP server status with active flag.

    Raises:
        HTTPException(500): If the status check fails unexpectedly.
    """
    try:
        data = await dhcp.dhcp_status()
        return DhcpStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/leases", response_model=DhcpLeasesResponse)
async def dhcp_leases(_key: str = ApiKey):
    """List all active DHCP leases.

    Parses the DHCP lease file and returns currently active leases
    including IP address, MAC address, hostname, and expiry time.

    Returns:
        DhcpLeasesResponse: List of active DHCP leases.

    Raises:
        HTTPException(500): If the lease file cannot be read or parsed.
    """
    try:
        data = await dhcp.dhcp_leases()
        return DhcpLeasesResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/relay/status", response_model=DhcpRelayStatusResponse)
async def relay_status(_key: str = ApiKey):
    """Retrieve the current DHCP relay agent status.

    Checks whether the DHCP relay process is active and returns its
    upstream server configuration.

    Returns:
        DhcpRelayStatusResponse: Relay daemon status and configuration.

    Raises:
        HTTPException(500): If the status check fails unexpectedly.
    """
    try:
        data = await dhcp.relay_status()
        return DhcpRelayStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/restart", response_model=DhcpActionResponse)
async def dhcp_restart(_key: str = ApiKey):
    """Restart the DHCP server process.

    Issues a ``systemctl restart`` for the ISC DHCP server and returns
    the operation result.

    Returns:
        DhcpActionResponse: Success status and result message.

    Raises:
        HTTPException(500): If the restart operation fails.
    """
    try:
        data = await dhcp.dhcp_restart()
        return DhcpActionResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/relay/restart", response_model=DhcpActionResponse)
async def relay_restart(_key: str = ApiKey):
    """Restart the DHCP relay agent process.

    Issues a ``systemctl restart`` for the DHCP relay service and
    returns the operation result.

    Returns:
        DhcpActionResponse: Success status and result message.

    Raises:
        HTTPException(500): If the restart operation fails.
    """
    try:
        data = await dhcp.relay_restart()
        return DhcpActionResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
