"""Event handler management API endpoints.

Provides REST endpoints for registering, removing, and firing
webhook/script event hooks on the BNG host.  Supports hook lifecycle
management, manual event triggering, and event history inspection.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey
from ..models.schemas import (
    ClearHistoryResponse,
    EventHistoryResponse,
    EventHookListResponse,
    EventHookRequest,
    EventHookResponse,
    FireEventRequest,
    FireEventResponse,
)
from ..services import event_handler

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/events", tags=["event-handler"])


@router.get("/hooks", response_model=EventHookListResponse)
async def list_hooks(_key: str = ApiKey):
    """List all registered event hooks.

    Returns every hook currently registered in the event handler,
    including its name, target event, action type, and enabled state.

    Returns:
        EventHookListResponse: Count and list of registered hooks.
    """
    hooks = event_handler.list_hooks()
    return EventHookListResponse(count=len(hooks), hooks=hooks)


@router.post("/hooks", status_code=201, response_model=EventHookResponse)
async def add_hook(req: EventHookRequest, _key: str = ApiKey):
    """Register a new event hook.

    Creates a hook that will execute the specified action (webhook URL
    or shell script) whenever the named event fires.

    Args:
        req: Hook definition including name, event, action, and enabled flag.

    Returns:
        EventHookResponse: The newly created hook details.

    Raises:
        HTTPException(409): If a hook with the same name already exists.
    """
    try:
        hook = event_handler.add_hook(
            name=req.name,
            event=req.event,
            action=req.action,
            enabled=req.enabled,
        )
        return EventHookResponse(**hook)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/hooks/{name}", status_code=204)
async def remove_hook(name: str, _key: str = ApiKey):
    """Remove an event hook by name.

    Unregisters the hook so it will no longer fire on future events.

    Args:
        name: The unique name of the hook to remove.

    Raises:
        HTTPException(404): If no hook with the given name exists.
    """
    try:
        event_handler.remove_hook(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/fire", response_model=FireEventResponse)
async def fire_event(req: FireEventRequest, _key: str = ApiKey):
    """Fire an event manually.

    Triggers all enabled hooks registered for the specified event type,
    passing the optional payload to each hook action.

    Args:
        req: Request body with event name and optional payload dict.

    Returns:
        FireEventResponse: Execution results from all triggered hooks.

    Raises:
        HTTPException(400): If the event name is invalid.
        HTTPException(500): If hook execution fails unexpectedly.
    """
    try:
        result = await event_handler.fire_event(req.event, req.payload)
        return FireEventResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history", response_model=EventHistoryResponse)
async def event_history(_key: str = ApiKey):
    """Retrieve the event history log.

    Returns a chronological list of all events that have been fired,
    including timestamps, event names, and execution outcomes.

    Returns:
        EventHistoryResponse: Count and list of history entries.
    """
    entries = event_handler.event_history()
    return EventHistoryResponse(count=len(entries), entries=entries)


@router.delete("/history", response_model=ClearHistoryResponse)
async def clear_history(_key: str = ApiKey):
    """Clear the event history log.

    Removes all recorded event history entries and returns the number
    of entries that were cleared.

    Returns:
        ClearHistoryResponse: Number of entries cleared.
    """
    count = event_handler.clear_history()
    return ClearHistoryResponse(cleared=count)
