"""PPPoE session management API endpoints.

Provides REST endpoints for listing active PPPoE sessions, viewing
session statistics and IP pool usage, finding sessions by username,
and terminating PPPoE sessions.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    SessionListResponse,
    SessionStatsResponse,
    TerminateRequest,
    TerminateResponse,
)
from ..services import accel

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(_key: str = ViewerKey):
    """List all active PPPoE sessions.

    Runs ``accel-cmd show sessions`` and returns a structured list
    of every active session with interface, username, IP, and state.

    Returns:
        SessionListResponse: Count and list of session records.

    Raises:
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        sessions = await accel.show_sessions()
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stats", response_model=SessionStatsResponse)
async def session_stats(_key: str = ViewerKey):
    """Return session statistics and IP pool usage.

    Combines ``accel-cmd show stat`` and ``accel-cmd show ippool``
    to return active/starting/finishing counts, CPU usage, pool
    utilisation, and uptime.

    Returns:
        SessionStatsResponse: Aggregate session and pool metrics.

    Raises:
        HTTPException(500): If the accel-cmd commands fail.
    """
    try:
        stat = await accel.show_stat()
        pool = await accel.show_ippool()

        return SessionStatsResponse(
            active=stat["sessions"]["active"],
            starting=stat["sessions"]["starting"],
            finishing=stat["sessions"]["finishing"],
            cpu_percent=stat["cpu"],
            pool_used=pool["used"],
            pool_total=pool["total"],
            uptime=stat["uptime"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/find/{username}", response_model=SessionListResponse)
async def find_session(username: str, _key: str = ViewerKey):
    """Find sessions for a specific username.

    Runs ``accel-cmd show sessions match username ^<user>$`` with
    extended column output and returns matching session records.

    Args:
        username: The PPPoE username to search for (path parameter).

    Returns:
        SessionListResponse: Count and list of matching sessions.

    Raises:
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        cols = "ifname,username,ip,calling-sid,rate-limit,type,state,uptime,rx-bytes,tx-bytes"
        output = await accel.run_cmd(
            f"show sessions match username ^{username}$ {cols}"
        )
        sessions = accel.parse_table(output)
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/terminate", response_model=TerminateResponse)
async def terminate_session(req: TerminateRequest, _key: str = ApiKey):
    """Terminate a PPPoE session by username or interface name.

    At least one of ``username`` or ``ifname`` must be provided.
    The matching session is terminated immediately.

    Args:
        req: Request body with username and/or ifname.

    Returns:
        TerminateResponse: Success flag and confirmation message.

    Raises:
        HTTPException(400): If neither username nor ifname is provided.
    """
    if not req.username and not req.ifname:
        raise HTTPException(status_code=400, detail="Provide username or ifname")

    try:
        await accel.terminate_session(username=req.username, ifname=req.ifname)
        target = req.username or req.ifname
        return TerminateResponse(success=True, message=f"Session {target} terminated")
    except Exception as exc:
        return TerminateResponse(success=False, message=str(exc))
