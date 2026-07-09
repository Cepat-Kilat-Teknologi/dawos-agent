"""NTP time synchronisation API endpoints.

Provides REST endpoints for querying NTP synchronisation status and
time sources via ``chronyc`` on the BNG host.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ViewerKey
from ..models.schemas import NtpSourcesResponse, NtpStatusResponse
from ..services import ntp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ntp", tags=["ntp"])


@router.get("/status", response_model=NtpStatusResponse)
async def ntp_status_endpoint(_key: str = ViewerKey):
    """Return NTP synchronisation status.

    Runs ``chronyc tracking`` and returns the current sync state,
    stratum, reference ID, and offset information.

    Returns:
        NtpStatusResponse: Synchronisation details from chrony.

    Raises:
        HTTPException(500): If the chronyc command fails.
    """
    try:
        data = await ntp.ntp_status()
        return NtpStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sources", response_model=NtpSourcesResponse)
async def ntp_sources_endpoint(_key: str = ViewerKey):
    """Return NTP time sources.

    Runs ``chronyc sources`` and returns a list of configured NTP
    servers with their state, stratum, poll interval, and offset.

    Returns:
        NtpSourcesResponse: List of NTP source records.

    Raises:
        HTTPException(500): If the chronyc command fails.
    """
    try:
        data = await ntp.ntp_sources()
        return NtpSourcesResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
