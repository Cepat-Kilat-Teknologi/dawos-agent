"""IP pool management API endpoints.

Provides REST endpoints for listing, adding, and removing IP address
pools used by accel-ppp for PPPoE subscriber address assignment.
Changes trigger an automatic accel-ppp config reload.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey
from ..models.schemas import (
    AddPoolRequest,
    IpPoolListResponse,
    PoolUsageResponse,
    RemovePoolResponse,
)
from ..services import ip_pool
from ..services.accel import reload_config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ip-pool", tags=["ip-pool"])


@router.get("", response_model=IpPoolListResponse)
async def list_pools(_key: str = ApiKey):
    """List all configured IP address pools.

    Reads the ``[ip-pool]`` section of the accel-ppp configuration
    and returns every defined pool with its name and IP range.

    Returns:
        IpPoolListResponse: Count and list of configured pools.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the pool list cannot be read.
    """
    try:
        pools = ip_pool.list_pools()
        return IpPoolListResponse(count=len(pools), pools=pools)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", status_code=201, response_model=RemovePoolResponse)
async def add_pool(req: AddPoolRequest, _key: str = ApiKey):
    """Add a new IP pool and reload accel-ppp.

    Appends a pool entry to the ``[ip-pool]`` config section and
    triggers a graceful accel-ppp reload to activate the new pool.

    Args:
        req: Request body with pool name and IP range.

    Returns:
        RemovePoolResponse: Success status and confirmation message.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(409): If a pool with the same name already exists.
        HTTPException(500): If the write or reload fails.
    """
    try:
        msg = ip_pool.add_pool(name=req.name, ip_range=req.ip_range)
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("Pool added but reload failed: %s", reload_exc)
            msg += " (reload failed)"

        return RemovePoolResponse(success=True, message=msg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{name}", status_code=204)
async def remove_pool(name: str, _key: str = ApiKey):
    """Remove an IP pool by name and reload accel-ppp.

    Deletes the named pool from the ``[ip-pool]`` config section and
    triggers a graceful accel-ppp reload.

    Args:
        name: The pool name to remove.

    Raises:
        HTTPException(404): If the pool or config file is not found.
        HTTPException(500): If the removal or reload fails.
    """
    try:
        ip_pool.remove_pool(name=name)
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("Pool removed but reload failed: %s", reload_exc)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/usage", response_model=PoolUsageResponse)
async def pool_usage(_key: str = ApiKey):
    """Get real-time IP pool utilisation statistics.

    Queries accel-ppp via ``accel-cmd show ippool`` and returns per-pool
    used/total counts and overall utilisation percentage.

    Returns:
        PoolUsageResponse: Per-pool and aggregate usage statistics.

    Raises:
        HTTPException(500): If the usage data cannot be retrieved.
    """
    try:
        data = await ip_pool.pool_usage()
        return PoolUsageResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
