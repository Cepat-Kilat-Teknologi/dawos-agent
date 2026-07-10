"""Session control API endpoints.

Provides granular PPPoE session management beyond basic terminate:
session lookup by SID or IP, detailed session snapshots with traffic
counters, session restart (terminate-and-reconnect), and bulk drop
by MAC address.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path

from ..auth import ApiKey, ViewerKey
from ..constants import RE_SAFE_MATCH, RE_SAFE_NAME
from ..models.schemas import (
    DropByMacRequest,
    DropByMacResponse,
    RestartSessionRequest,
    RestartSessionResponse,
    SessionByIdResponse,
    SessionSnapshotResponse,
)
from ..services import session_control

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions/control", tags=["session-control"])


@router.get("/by-sid/{sid}", response_model=SessionByIdResponse)
async def get_session_by_sid(
    sid: str = Path(pattern=RE_SAFE_MATCH), _key: str = ViewerKey
):
    """Look up a PPPoE session by accel-ppp session ID.

    Searches active sessions for the given SID and returns the
    full session record if found.

    Args:
        sid: The accel-ppp session ID (path parameter).

    Returns:
        SessionByIdResponse: Found flag and session record (or null).

    Raises:
        HTTPException(500): If the session lookup fails.
    """
    try:
        session = await session_control.session_by_sid(sid)
        return SessionByIdResponse(
            found=session is not None,
            session=session,
        )
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/by-ip/{ip}", response_model=SessionByIdResponse)
async def get_session_by_ip(
    ip: str = Path(pattern=RE_SAFE_MATCH), _key: str = ViewerKey
):
    """Look up a PPPoE session by assigned IP address.

    Searches active sessions for the given IP and returns the
    full session record if found.

    Args:
        ip: The assigned IP address (path parameter).

    Returns:
        SessionByIdResponse: Found flag and session record (or null).

    Raises:
        HTTPException(500): If the session lookup fails.
    """
    try:
        session = await session_control.session_by_ip(ip)
        return SessionByIdResponse(
            found=session is not None,
            session=session,
        )
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/snapshot/{username}", response_model=SessionSnapshotResponse)
async def session_snapshot(
    username: str = Path(pattern=RE_SAFE_NAME), _key: str = ViewerKey
):
    """Get a detailed session snapshot with traffic counters.

    Returns comprehensive session information including interface
    name, IP, calling-station-id, rate-limit, uptime, and
    rx/tx byte counters.

    Args:
        username: The PPPoE username to snapshot (path parameter).

    Returns:
        SessionSnapshotResponse: Detailed session data with counters.

    Raises:
        HTTPException(500): If the snapshot cannot be retrieved.
    """
    try:
        snap = await session_control.session_snapshot(username)
        return SessionSnapshotResponse(**snap)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/restart", response_model=RestartSessionResponse)
async def restart_session(req: RestartSessionRequest, _key: str = ApiKey):
    """Terminate a PPPoE session so the CPE reconnects.

    Sends a terminate command for the given username, causing the
    subscriber's CPE to re-initiate the PPPoE discovery process.

    Args:
        req: Request body with the username to restart.

    Returns:
        RestartSessionResponse: Success flag and result details.

    Raises:
        HTTPException(500): If the terminate command fails.
    """
    try:
        result = await session_control.restart_session(req.username)
        return RestartSessionResponse(**result)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/drop-by-mac", response_model=DropByMacResponse)
async def drop_by_mac(req: DropByMacRequest, _key: str = ApiKey):
    """Drop all PPPoE sessions from a specific MAC address.

    Terminates every active session whose calling-station-id matches
    the given MAC, useful for clearing stale or duplicate sessions
    from a single CPE device.

    Args:
        req: Request body with the MAC address to drop.

    Returns:
        DropByMacResponse: Count of dropped sessions and result.

    Raises:
        HTTPException(500): If the drop operation fails.
    """
    try:
        result = await session_control.drop_by_mac(req.mac)
        return DropByMacResponse(**result)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
