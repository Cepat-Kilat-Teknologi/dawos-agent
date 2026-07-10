"""Log retrieval and streaming API endpoints.

Provides REST endpoints for tailing recent log lines from systemd
journal units and streaming live log output via Server-Sent Events
(SSE).  Primarily used for real-time accel-ppp log monitoring.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..auth import ViewerKey
from ..constants import RE_SAFE_NAME
from ..models.schemas import LogResponse
from ..services import logs

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("/tail", response_model=LogResponse)
async def tail_logs(
    lines: int = Query(default=100, ge=1, le=10000),
    unit: str = Query(default="accel-ppp", pattern=RE_SAFE_NAME),
    _key: str = ViewerKey,
):
    """Return the last N log lines from a systemd journal unit.

    Fetches recent log entries using ``journalctl -u <unit>`` and
    returns them as a list of strings.

    Args:
        lines: Number of trailing log lines to return (default 100).
        unit: Systemd unit name to query (default ``accel-ppp``).

    Returns:
        LogResponse: List of log lines and metadata.

    Raises:
        HTTPException(500): If the journalctl command fails.
    """
    try:
        data = await logs.get_logs(lines=lines, unit=unit)
        return LogResponse(**data)
    except RuntimeError as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/stream")
async def stream_logs(
    unit: str = Query(default="accel-ppp", pattern=RE_SAFE_NAME),
    _key: str = ViewerKey,
):
    """Stream live log lines via Server-Sent Events (SSE).

    Opens a persistent ``journalctl -f -u <unit>`` process and streams
    each new log line as an SSE event.  The connection remains open
    until the client disconnects.

    Args:
        unit: Systemd unit name to stream (default ``accel-ppp``).

    Returns:
        StreamingResponse: SSE stream with ``text/event-stream`` content type.
    """
    return StreamingResponse(
        logs.log_stream_events(unit=unit),
        media_type="text/event-stream",
    )
