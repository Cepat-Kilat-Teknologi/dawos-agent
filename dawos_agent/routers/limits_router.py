"""Connection limits management API endpoints.

Provides REST endpoints for reading and updating session and rate-limit
caps in the accel-ppp configuration.  Supports global session limits
and per-interface PADI rate limiting.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    ConnectionLimitsResponse,
    InterfaceLimitResponse,
    SetLimitsRequest,
)
from ..services import connection_limits
from ..services.accel import reload_config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/limits", tags=["connection-limits"])


@router.get("", response_model=ConnectionLimitsResponse)
async def get_limits(_key: str = ViewerKey):
    """Read global session limits from the accel-ppp configuration.

    Returns the current ``max-sessions`` and ``max-starting`` values
    from the config file.

    Returns:
        ConnectionLimitsResponse: Current limit values.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the limits cannot be read.
    """
    try:
        data = connection_limits.get_limits()
        return ConnectionLimitsResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("", response_model=ConnectionLimitsResponse)
async def set_limits(req: SetLimitsRequest, _key: str = ApiKey):
    """Update global session limits and reload accel-ppp.

    Writes the new ``max-sessions`` and ``max-starting`` values to the
    config file and triggers a graceful reload.

    Args:
        req: Request body with max_sessions and max_starting values.

    Returns:
        ConnectionLimitsResponse: Updated limit values after reload.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the update or reload fails.
    """
    try:
        connection_limits.set_limits(
            max_sessions=req.max_sessions,
            max_starting=req.max_starting,
        )
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("Limits saved but reload failed: %s", reload_exc)

        data = connection_limits.get_limits()
        return ConnectionLimitsResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/interface/{name}", response_model=InterfaceLimitResponse)
async def get_interface_limit(name: str, _key: str = ViewerKey):
    """Read the PADI rate-limit for a specific PPPoE interface.

    Returns the ``padi-limit`` value configured for the named interface
    in the ``[pppoe]`` config section.

    Args:
        name: The PPPoE interface name to query.

    Returns:
        InterfaceLimitResponse: Interface name and its PADI limit value.

    Raises:
        HTTPException(404): If the config file or interface is not found.
        HTTPException(500): If the limit cannot be read.
    """
    try:
        data = connection_limits.get_interface_limit(name)
        return InterfaceLimitResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
