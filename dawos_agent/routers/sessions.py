"""PPPoE session management API endpoints.

Provides REST endpoints for listing active PPPoE sessions, viewing
session statistics and IP pool usage, finding sessions by username,
and terminating PPPoE sessions.

The ``GET /sessions`` and ``GET /sessions/find/{username}`` endpoints
accept an optional ``?columns=`` query parameter to select which
accel-cmd columns to return.  Unknown column names are rejected with
HTTP 422.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging
import shlex

from fastapi import APIRouter, HTTPException, Path, Query

from ..auth import ApiKey, ViewerKey
from ..constants import (
    COLUMNS_DEFAULT,
    COLUMNS_EXTENDED,
    RE_SAFE_COLUMNS,
    RE_SAFE_IP,
    RE_SAFE_MAC,
    RE_SAFE_MATCH,
    RE_SAFE_NAME,
)
from ..models.schemas import (
    SessionListResponse,
    SessionStatsResponse,
    TerminateRequest,
    TerminateResponse,
)
from ..services import accel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _resolve_columns(columns: str | None) -> str:
    """Map the user-supplied ``columns`` query parameter to a safe value.

    Args:
        columns: Raw query parameter — ``None`` (omitted), ``"all"``, or
            a comma-separated list of column names.

    Returns:
        A validated comma-separated column string.
    """
    if columns is None:
        return COLUMNS_DEFAULT
    if columns.strip().lower() == "all":
        return COLUMNS_EXTENDED
    # validate_columns() raises ValueError for invalid names.
    return accel.validate_columns(columns)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    columns: str | None = Query(
        None,
        pattern=RE_SAFE_COLUMNS,
        description=(
            "Comma-separated column names to include.  "
            "Use 'all' for all available columns.  "
            "Omit for the default set."
        ),
    ),
    _key: str = ViewerKey,
):
    """List all active PPPoE sessions.

    Runs ``accel-cmd show sessions`` and returns a structured list
    of every active session with interface, username, IP, and state.

    The optional ``columns`` query parameter selects which fields
    to include.  Pass ``all`` to get every available column, or a
    comma-separated list of specific column names.

    Returns:
        SessionListResponse: Count and list of session records.

    Raises:
        HTTPException(422): If *columns* contains invalid column names.
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        cols = _resolve_columns(columns)
        sessions = await accel.show_sessions(columns=cols)
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


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
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/find/{username}", response_model=SessionListResponse)
async def find_session(
    username: str = Path(pattern=RE_SAFE_NAME),
    columns: str | None = Query(
        None,
        pattern=RE_SAFE_COLUMNS,
        description="Comma-separated columns or 'all'.  Omit for default.",
    ),
    _key: str = ViewerKey,
):
    """Find sessions for a specific username.

    Runs ``accel-cmd show sessions match username ^<user>$`` with
    the selected columns and returns matching session records.

    Args:
        username: The PPPoE username to search for (path parameter).
        columns: Optional column selection (query parameter).

    Returns:
        SessionListResponse: Count and list of matching sessions.

    Raises:
        HTTPException(422): If *columns* contains invalid column names.
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        cols = _resolve_columns(columns)
        output = await accel.run_cmd(
            f"show sessions match username ^{shlex.quote(username)}$ {cols}"
        )
        sessions = accel.parse_table(output)
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# Session search — by MAC / IP / SID (P0.3)
# ---------------------------------------------------------------------------


@router.get("/search/mac/{mac}", response_model=SessionListResponse)
async def search_by_mac(
    mac: str = Path(pattern=RE_SAFE_MAC),
    columns: str | None = Query(
        None,
        pattern=RE_SAFE_COLUMNS,
        description="Comma-separated columns or 'all'.  Omit for default.",
    ),
    _key: str = ViewerKey,
):
    """Search sessions by calling-station-id (MAC address).

    Runs ``accel-cmd show sessions match calling-sid <mac>`` and returns
    all sessions originating from the given MAC address.

    Args:
        mac: MAC address in ``AA:BB:CC:DD:EE:FF`` format (path parameter).
        columns: Optional column selection (query parameter).

    Returns:
        SessionListResponse: Count and list of matching sessions.

    Raises:
        HTTPException(422): If *columns* contains invalid column names.
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        cols = _resolve_columns(columns)
        sessions = await accel.search_sessions("calling-sid", mac, columns=cols)
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/search/ip/{ip}", response_model=SessionListResponse)
async def search_by_ip(
    ip: str = Path(pattern=RE_SAFE_IP),
    columns: str | None = Query(
        None,
        pattern=RE_SAFE_COLUMNS,
        description="Comma-separated columns or 'all'.  Omit for default.",
    ),
    _key: str = ViewerKey,
):
    """Search sessions by assigned IP address.

    Runs ``accel-cmd show sessions match ip <ip>`` and returns all
    sessions with the given IP address.

    Args:
        ip: IPv4 or IPv6 address (path parameter).
        columns: Optional column selection (query parameter).

    Returns:
        SessionListResponse: Count and list of matching sessions.

    Raises:
        HTTPException(422): If *columns* contains invalid column names.
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        cols = _resolve_columns(columns)
        sessions = await accel.search_sessions("ip", ip, columns=cols)
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/search/sid/{sid}", response_model=SessionListResponse)
async def search_by_sid(
    sid: str = Path(pattern=RE_SAFE_MATCH),
    columns: str | None = Query(
        None,
        pattern=RE_SAFE_COLUMNS,
        description="Comma-separated columns or 'all'.  Omit for default.",
    ),
    _key: str = ViewerKey,
):
    """Search sessions by accel-ppp session ID.

    Runs ``accel-cmd show sessions match sid <sid>`` and returns all
    sessions matching the given session identifier.

    Args:
        sid: The accel-ppp session ID (path parameter).
        columns: Optional column selection (query parameter).

    Returns:
        SessionListResponse: Count and list of matching sessions.

    Raises:
        HTTPException(422): If *columns* contains invalid column names.
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        cols = _resolve_columns(columns)
        sessions = await accel.search_sessions("sid", sid, columns=cols)
        return SessionListResponse(count=len(sessions), sessions=sessions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


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
        HTTPException(500): If the terminate command fails.
    """
    if not req.username and not req.ifname:
        raise HTTPException(status_code=400, detail="Provide username or ifname")

    try:
        await accel.terminate_session(username=req.username, ifname=req.ifname)
        target = req.username or req.ifname
        return TerminateResponse(success=True, message=f"Session {target} terminated")
    except Exception as exc:
        # Raise 500 on failure (consistent with the session-control endpoints)
        # instead of a false 200 + success:false that callers miss (DA-M08).
        log.error("Session terminate failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
