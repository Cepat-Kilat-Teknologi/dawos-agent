"""WebSocket endpoint for real-time event streaming.

Provides a bidirectional WebSocket connection at ``/ws/events`` that
pushes server-side events (session changes, config mutations, audit
trail, system lifecycle) to connected clients in real time.

Authentication
--------------
WebSocket connections authenticate via the ``X-API-Key`` header
(preferred) or the ``key`` query parameter (browser fallback)::

    # Header (preferred — does not leak to access logs)
    ws = new WebSocket("ws://host:8470/ws/events")
    // with custom headers via a library that supports it

    # Query parameter (browser WebSocket API fallback)
    ws://host:8470/ws/events?key=YOUR_API_KEY

The minimum required role is **viewer** (read-only access).

Protocol
--------
After connection, the client may send JSON control messages:

Subscribe to specific channels::

    {"action": "subscribe", "channels": ["session", "config"]}

Unsubscribe::

    {"action": "unsubscribe", "channels": ["session"]}

Ping (keepalive)::

    {"action": "ping"}

The server responds with JSON event messages::

    {
        "channel": "session",
        "type": "session.connect",
        "data": {"username": "user1", "ip": "10.0.0.1"},
        "timestamp": "2026-07-09T12:00:00+00:00"
    }

Available channels: ``session``, ``config``, ``audit``, ``system``.
Use ``all`` to receive events from every channel.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..auth import get_resolver
from ..events import CHANNELS, bus
from ..rbac import Role, role_has_access

log = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _authenticate(websocket: WebSocket, key: str | None) -> bool:
    """Validate the API key and accept or reject the connection.

    Resolution order (DA-M02), preferring transports that do **not**
    leak the key into access logs:

    1. ``X-API-Key`` header — non-browser clients (CLI, server proxy).
    2. ``Sec-WebSocket-Protocol`` header — browsers, which cannot set
       custom headers but *can* pass a subprotocol token.
    3. ``key`` query parameter — legacy fallback (visible in access logs).

    Returns ``True`` if the connection was accepted, ``False`` if
    rejected (the socket is closed with 1008 Policy Violation).
    """
    # Prefer header/subprotocol auth to avoid query-string log exposure.
    resolved_key = (
        websocket.headers.get("x-api-key")
        or websocket.headers.get("sec-websocket-protocol")
        or key
    )

    if not resolved_key:
        await websocket.close(code=1008, reason="Missing API key")
        return False

    resolver = get_resolver()
    role = resolver.resolve(resolved_key)

    if role is None:
        await websocket.close(code=1008, reason="Invalid API key")
        return False

    if not role_has_access(role, Role.VIEWER):
        await websocket.close(code=1008, reason="Insufficient permissions")
        return False

    await websocket.accept()
    return True


async def _handle_control(
    data: dict,
    queue: asyncio.Queue,
    subscribed: set,
    websocket: WebSocket,
) -> None:
    """Process a client control message (subscribe/unsubscribe/ping)."""
    action = data.get("action", "")

    if action == "ping":
        await websocket.send_json({"action": "pong"})
        return

    channels = data.get("channels", [])
    if not isinstance(channels, list):
        await websocket.send_json({"error": "channels must be a list"})
        return

    if action == "subscribe":
        targets = set(channels) & (CHANNELS | {"all"})
        if "all" in targets:
            targets = CHANNELS
        # Re-subscribe: add queue to new channels on the bus.
        for ch in targets:
            bus.add_to_channel(ch, queue)
            subscribed.add(ch)
        await websocket.send_json(
            {"action": "subscribed", "channels": sorted(subscribed)}
        )

    elif action == "unsubscribe":
        targets = set(channels) & subscribed
        for ch in targets:
            bus.remove_from_channel(ch, queue)
            subscribed.discard(ch)
        await websocket.send_json(
            {"action": "unsubscribed", "channels": sorted(subscribed)}
        )

    else:
        await websocket.send_json({"error": f"Unknown action: {action}"})


@router.websocket("/ws/events")
async def ws_events(
    websocket: WebSocket,
    key: str | None = Query(default=None),
) -> None:
    """Stream real-time events over WebSocket.

    Authenticates via the ``X-API-Key`` header (preferred) or the
    ``key`` query parameter (browser fallback), then subscribes to
    all channels by default.  Clients can refine subscriptions with
    JSON control messages after connection.
    """
    if not await _authenticate(websocket, key):
        return

    # Default: subscribe to all channels.
    subscribed: set = set(CHANNELS)
    queue = bus.subscribe({"all"})

    log.info("WebSocket client connected (subscribed to all channels)")

    try:
        # Two concurrent tasks: push events and listen for control messages.
        push_task = asyncio.create_task(_push_events(websocket, queue))
        recv_task = asyncio.create_task(_receive_control(websocket, queue, subscribed))

        # Wait until either task finishes (disconnect or error).
        done, pending = await asyncio.wait(
            {push_task, recv_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Re-raise any exception from completed tasks.
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc

    except WebSocketDisconnect:  # pragma: no cover — race with task cancel
        log.info("WebSocket client disconnected")
    finally:
        bus.unsubscribe(queue)
        log.info("WebSocket client cleaned up")


async def _push_events(
    websocket: WebSocket,
    queue: asyncio.Queue,
) -> None:
    """Read events from the queue and push to the WebSocket client."""
    while True:
        event = await queue.get()
        await websocket.send_json(event)


async def _receive_control(
    websocket: WebSocket,
    queue: asyncio.Queue,
    subscribed: set,
) -> None:
    """Listen for client control messages."""
    while True:
        raw = await websocket.receive_text()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"error": "Invalid JSON"})
            continue

        if not isinstance(data, dict):
            await websocket.send_json({"error": "Expected JSON object"})
            continue

        await _handle_control(data, queue, subscribed, websocket)
