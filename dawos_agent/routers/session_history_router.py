"""Session history API endpoints.

Provides REST endpoints for capturing, querying, and managing
historical PPPoE session snapshots stored in a local SQLite database.
Snapshots record the state of all active sessions at a point in time
so operators can review session history after sessions have ended.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    SessionHistoryResponse,
    SessionHistoryStatsResponse,
    SessionSnapshotResult,
)
from ..services import session_history

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions/history", tags=["session-history"])


@router.get("", response_model=SessionHistoryResponse)
async def get_history(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    username: str | None = Query(None, description="Filter by exact username"),
    ip: str | None = Query(None, description="Filter by exact IP address"),
    start: str | None = Query(None, description="ISO-8601 lower bound"),
    end: str | None = Query(None, description="ISO-8601 upper bound"),
    limit: int = Query(100, ge=1, le=1000, description="Max records per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _key: str = ViewerKey,
):
    """Query session history with optional filters.

    Returns paginated session history records from the SQLite database.
    Supports filtering by username, IP address, and time range.

    Args:
        username: Optional exact username match.
        ip: Optional exact IP address match.
        start: Optional ISO-8601 lower bound for snapshot timestamp.
        end: Optional ISO-8601 upper bound for snapshot timestamp.
        limit: Maximum records to return (1-1000, default 100).
        offset: Pagination offset (default 0).

    Returns:
        SessionHistoryResponse: Paginated list of history records.

    Raises:
        HTTPException(500): If the database cannot be read.
    """
    try:
        data = await session_history.query_history(
            username=username,
            ip=ip,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        return SessionHistoryResponse(**data)
    except Exception as exc:
        log.error("Failed to query session history: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/snapshot", response_model=SessionSnapshotResult)
async def take_snapshot(_key: str = ApiKey):
    """Capture a snapshot of all active PPPoE sessions.

    Queries ``accel-cmd show sessions`` and stores every active session
    record in the history database with the current UTC timestamp.

    Returns:
        SessionSnapshotResult: Number of sessions captured and timestamp.

    Raises:
        HTTPException(500): If the snapshot fails.
    """
    try:
        data = await session_history.snapshot_sessions()
        return SessionSnapshotResult(**data)
    except Exception as exc:
        log.error("Failed to take session snapshot: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete("")
async def purge(
    before: str = Query(..., description="ISO-8601 cutoff timestamp"),
    _key: str = ApiKey,
):
    """Purge session history records older than the given timestamp.

    Deletes all records with ``snapshot_at < before``.  This is a
    destructive operation intended for disk management and GDPR
    compliance.

    Args:
        before: ISO-8601 timestamp cutoff.

    Returns:
        dict: Number of records deleted.

    Raises:
        HTTPException(500): If the purge fails.
    """
    try:
        deleted = await session_history.purge_history(before=before)
        return {"deleted": deleted}
    except Exception as exc:
        log.error("Failed to purge session history: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/stats", response_model=SessionHistoryStatsResponse)
async def get_stats(_key: str = ViewerKey):
    """Get aggregate statistics for the session history database.

    Returns record counts, unique users, date range, and database
    file size.

    Returns:
        SessionHistoryStatsResponse: History database statistics.

    Raises:
        HTTPException(500): If the stats cannot be retrieved.
    """
    try:
        data = await session_history.history_stats()
        return SessionHistoryStatsResponse(**data)
    except Exception as exc:
        log.error("Failed to get history stats: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
