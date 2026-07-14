"""Bulk CSV export API endpoints.

Provides endpoints for downloading active PPPoE sessions and
historical session snapshots as CSV files.  Responses use
``text/csv`` content type with a ``Content-Disposition`` header
so browsers trigger a file download.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..auth import ViewerKey
from ..services import csv_export

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/sessions")
async def export_sessions(_key: str = ViewerKey):
    """Export all active PPPoE sessions as a CSV download.

    Fetches the current session table from ``accel-cmd show sessions``
    and returns it as an RFC 4180-compliant CSV file.  Cell values are
    sanitised to prevent spreadsheet formula injection.

    Returns:
        Response: CSV file with ``text/csv`` content type.

    Raises:
        HTTPException(500): If session data cannot be retrieved.
    """
    try:
        csv_data = await csv_export.export_sessions_csv()
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": ('attachment; filename="sessions.csv"'),
            },
        )
    except Exception as exc:
        log.error("Failed to export sessions CSV: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/history")
async def export_history(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    username: str | None = Query(None, description="Filter by username"),
    ip: str | None = Query(None, description="Filter by IP address"),
    start: str | None = Query(None, description="ISO-8601 lower bound"),
    end: str | None = Query(None, description="ISO-8601 upper bound"),
    limit: int = Query(10000, ge=1, le=50000, description="Max records to export"),
    _key: str = ViewerKey,
):
    """Export session history records as a CSV download.

    Queries the SQLite history database with optional filters and
    returns matching records as an RFC 4180-compliant CSV file.
    Cell values are sanitised to prevent spreadsheet formula injection.

    Args:
        username: Optional exact username match.
        ip: Optional exact IP address match.
        start: Optional ISO-8601 lower bound for snapshot timestamp.
        end: Optional ISO-8601 upper bound for snapshot timestamp.
        limit: Maximum records to export (1-50000, default 10000).

    Returns:
        Response: CSV file with ``text/csv`` content type.

    Raises:
        HTTPException(500): If history data cannot be retrieved.
    """
    try:
        csv_data = await csv_export.export_history_csv(
            username=username,
            ip=ip,
            start=start,
            end=end,
            limit=limit,
        )
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": ('attachment; filename="history.csv"'),
            },
        )
    except Exception as exc:
        log.error("Failed to export history CSV: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
