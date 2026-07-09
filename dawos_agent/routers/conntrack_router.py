"""Conntrack tuning API endpoints.

Provides REST endpoints for inspecting and tuning the Linux
``nf_conntrack`` subsystem on the BNG host.  Supports table-size
adjustment, per-protocol timeout management, helper module listing,
and predefined tuning profile application.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    ConntrackConfigResponse,
    ConntrackHelperResponse,
    ConntrackHelpersListResponse,
    ConntrackProfileRequest,
    ConntrackTableSizeRequest,
    ConntrackTimeoutRequest,
    ConntrackTimeoutsResponse,
)
from ..services import conntrack

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/conntrack", tags=["conntrack"])


@router.get("/config", response_model=ConntrackConfigResponse)
async def get_config(_key: str = ViewerKey):
    """Read current conntrack table configuration.

    Returns the ``nf_conntrack_max`` value, current entry count, and
    hash-table size from the kernel.

    Returns:
        ConntrackConfigResponse: Table size, current count, and hash size.

    Raises:
        HTTPException(500): If the kernel parameters cannot be read.
    """
    try:
        data = await conntrack.get_config()
        return ConntrackConfigResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/table-size", response_model=ConntrackConfigResponse)
async def set_table_size(req: ConntrackTableSizeRequest, _key: str = ApiKey):
    """Set the ``nf_conntrack_max`` table size.

    Updates the kernel sysctl value for the maximum number of tracked
    connections.  The change is applied immediately but is not persisted
    across reboots unless separately configured.

    Args:
        req: Request body containing the desired table size.

    Returns:
        ConntrackConfigResponse: Updated table configuration.

    Raises:
        HTTPException(500): If the sysctl write fails.
    """
    try:
        data = await conntrack.set_table_size(req.size)
        return ConntrackConfigResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/timeouts", response_model=ConntrackTimeoutsResponse)
async def get_timeouts(_key: str = ViewerKey):
    """Read all conntrack protocol timeouts.

    Returns the current timeout values for all tracked protocols
    (TCP, UDP, ICMP, generic) from the kernel sysctl tree.

    Returns:
        ConntrackTimeoutsResponse: Dictionary of protocol timeout values.

    Raises:
        HTTPException(500): If the timeout values cannot be read.
    """
    try:
        data = await conntrack.get_timeouts()
        return ConntrackTimeoutsResponse(timeouts=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/timeouts", response_model=ConntrackTimeoutsResponse)
async def set_timeout(req: ConntrackTimeoutRequest, _key: str = ApiKey):
    """Set a single conntrack timeout value.

    Updates an individual protocol timeout (e.g.
    ``nf_conntrack_tcp_timeout_established``) to the specified number
    of seconds.

    Args:
        req: Request body containing the sysctl key and timeout in seconds.

    Returns:
        ConntrackTimeoutsResponse: Updated timeout map.

    Raises:
        HTTPException(400): If the key is invalid or the value is out of range.
        HTTPException(500): If the sysctl write fails.
    """
    try:
        data = await conntrack.set_timeout(req.key, req.seconds)
        return ConntrackTimeoutsResponse(timeouts=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/helpers", response_model=ConntrackHelpersListResponse)
async def list_helpers(_key: str = ViewerKey):
    """List loaded conntrack helper (ALG) modules.

    Enumerates kernel modules that provide application-layer gateway
    support for protocols such as FTP, SIP, and H.323.

    Returns:
        ConntrackHelpersListResponse: Count and details of loaded helpers.

    Raises:
        HTTPException(500): If the helper list cannot be retrieved.
    """
    try:
        helpers = await conntrack.list_helpers()
        return ConntrackHelpersListResponse(
            count=len(helpers),
            helpers=[ConntrackHelperResponse(**h) for h in helpers],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/profiles")
async def list_profiles(_key: str = ViewerKey):
    """List available conntrack tuning profiles.

    Returns the names of predefined timeout profiles (e.g. ``bng``,
    ``default``) that can be applied via ``POST /profiles/apply``.

    Returns:
        dict: List of profile names.
    """
    names = conntrack.list_profiles()
    return {"profiles": names}


@router.post("/profiles/apply", response_model=ConntrackTimeoutsResponse)
async def apply_profile(req: ConntrackProfileRequest, _key: str = ApiKey):
    """Apply a named conntrack tuning profile.

    Writes all timeout values defined in the profile to the kernel
    sysctl tree in a single operation.

    Args:
        req: Request body containing the profile name to apply.

    Returns:
        ConntrackTimeoutsResponse: Updated timeout map after applying.

    Raises:
        HTTPException(400): If the profile name is unknown.
        HTTPException(500): If any sysctl write fails.
    """
    try:
        data = await conntrack.apply_profile(req.name)
        return ConntrackTimeoutsResponse(timeouts=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
