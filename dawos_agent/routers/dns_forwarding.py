"""DNS forwarding management API endpoints.

Provides REST endpoints for managing the dnsmasq DNS forwarding service
on the BNG host.  Supports status monitoring, upstream server
configuration, cache-size tuning, and cache flushing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey
from ..models.schemas import (
    DnsForwardingConfigResponse,
    DnsForwardingFlushResponse,
    DnsForwardingSetRequest,
    DnsForwardingStatusResponse,
)
from ..services import dns_forwarding

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dns/forwarding", tags=["dns-forwarding"])


@router.get("/status", response_model=DnsForwardingStatusResponse)
async def dns_fwd_status(_key: str = ApiKey):
    """Check the dnsmasq service status.

    Verifies whether the dnsmasq process is running and returns its
    operational state.

    Returns:
        DnsForwardingStatusResponse: Active flag and process details.

    Raises:
        HTTPException(500): If the status check fails unexpectedly.
    """
    try:
        data = await dns_forwarding.status()
        return DnsForwardingStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/config", response_model=DnsForwardingConfigResponse)
async def dns_fwd_config(_key: str = ApiKey):
    """Read the current DNS forwarding configuration.

    Returns the list of upstream DNS servers and the configured cache
    size from the dnsmasq configuration file.

    Returns:
        DnsForwardingConfigResponse: Upstream servers and cache size.

    Raises:
        HTTPException(500): If the configuration cannot be read.
    """
    try:
        data = await dns_forwarding.get_config()
        return DnsForwardingConfigResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/config", response_model=DnsForwardingConfigResponse)
async def set_dns_fwd(req: DnsForwardingSetRequest, _key: str = ApiKey):
    """Set upstream DNS servers and cache size.

    Writes the provided forwarder list and cache-size value to the
    dnsmasq configuration and restarts the service to apply changes.

    Args:
        req: Request body with upstream server list and cache size.

    Returns:
        DnsForwardingConfigResponse: Updated configuration after apply.

    Raises:
        HTTPException(500): If the configuration write or restart fails.
    """
    try:
        data = await dns_forwarding.set_forwarders(req.servers, req.cache_size)
        return DnsForwardingConfigResponse(**data)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/flush", response_model=DnsForwardingFlushResponse)
async def flush_dns_cache(_key: str = ApiKey):
    """Flush the dnsmasq DNS cache.

    Sends SIGHUP to the dnsmasq process to clear all cached DNS
    records, forcing fresh upstream lookups for subsequent queries.

    Returns:
        DnsForwardingFlushResponse: Success status and message.

    Raises:
        HTTPException(500): If the cache flush signal fails.
    """
    try:
        data = await dns_forwarding.flush_cache()
        return DnsForwardingFlushResponse(**data)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
