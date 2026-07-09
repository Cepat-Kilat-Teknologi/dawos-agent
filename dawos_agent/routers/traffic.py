"""Live traffic monitoring and shaper control API endpoints.

Provides REST endpoints and SSE streams for real-time per-user and
aggregate throughput monitoring, tc queue statistics, and runtime
rate-limit overrides on the PPP router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    QueueStats,
    RateLimitRequest,
    RateLimitResponse,
)
from ..services import traffic

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])


# ---------------------------------------------------------------------------
# SSE — per-user live traffic
# ---------------------------------------------------------------------------


@router.get("/stream/{username}")
async def stream_user_traffic(
    username: str,
    interval: float = 2.0,
    _key: str = ViewerKey,
):
    """Stream per-user throughput via Server-Sent Events (SSE).

    Opens a persistent connection and emits download/upload Mbps
    readings at the configured interval.  The stream ends
    automatically when the user's PPPoE session drops.

    Args:
        username: The PPPoE username to monitor (path parameter).
        interval: Sampling interval in seconds (default 2.0).

    Returns:
        StreamingResponse: SSE stream with ``text/event-stream``
            content type.
    """
    return StreamingResponse(
        traffic.user_traffic_events(username, interval=interval),
        media_type="text/event-stream",
    )


@router.get("/stream")
async def stream_aggregate_traffic(
    interval: float = 2.0,
    _key: str = ViewerKey,
):
    """Stream aggregate throughput via Server-Sent Events (SSE).

    Opens a persistent connection and emits per-session throughput
    for all active sessions, sorted by download speed descending.

    Args:
        interval: Sampling interval in seconds (default 2.0).

    Returns:
        StreamingResponse: SSE stream with ``text/event-stream``
            content type.
    """
    return StreamingResponse(
        traffic.aggregate_traffic_events(interval=interval),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Queue stats
# ---------------------------------------------------------------------------


@router.get("/queue/{username}", response_model=QueueStats)
async def queue_stats(username: str, _key: str = ViewerKey):
    """Return tc shaper queue statistics for a user's session.

    Queries the Linux tc subsystem for the traffic-control qdisc
    attached to the user's PPP interface and returns packet/byte
    counters, drop counts, and queue length.

    Args:
        username: The PPPoE username whose queue to inspect.

    Returns:
        QueueStats: Queue depth, packet counts, and byte counters.

    Raises:
        HTTPException(404): If the user has no active session.
        HTTPException(500): If the tc query fails.
    """
    try:
        data = await traffic.get_queue_stats(username)
        return QueueStats(**data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Ratelimit management
# ---------------------------------------------------------------------------


@router.post(
    "/ratelimit/{username}",
    response_model=RateLimitResponse,
)
async def change_ratelimit(
    username: str,
    req: RateLimitRequest,
    _key: str = ApiKey,
):
    """Temporarily override a session's shaper rate.

    Applies a new rate limit via ``accel-cmd shaper change`` that
    bypasses the RADIUS-assigned value.  The override persists until
    the session ends or is explicitly restored.

    Rate format: ``up/down`` e.g. ``5M/20M``.

    Args:
        username: The PPPoE username to rate-limit.
        req: Request body with the new rate string.

    Returns:
        RateLimitResponse: Success flag, message, username, and rate.

    Raises:
        HTTPException(404): If the user has no active session.
        HTTPException(500): If the shaper command fails.
    """
    try:
        msg = await traffic.change_ratelimit(username, req.rate)
        return RateLimitResponse(
            success=True,
            message=msg,
            username=username,
            rate=req.rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete(
    "/ratelimit/{username}",
    status_code=204,
)
async def restore_ratelimit(username: str, _key: str = ApiKey):
    """Restore a session's shaper to the RADIUS-assigned value.

    Reverts any temporary rate-limit override applied via the
    ``change_ratelimit`` endpoint.

    Args:
        username: The PPPoE username whose rate to restore.

    Raises:
        HTTPException(404): If the user has no active session.
        HTTPException(500): If the shaper restore command fails.
    """
    try:
        await traffic.restore_ratelimit(username)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
