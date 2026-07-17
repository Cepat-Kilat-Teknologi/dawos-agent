"""Event handler — webhook and script triggers for BNG session events.

In-memory registry of event hooks.  When a session lifecycle event
fires (session-up, session-down, etc.), all matching enabled handlers
execute — either as HTTP webhook POSTs or local shell commands.

Security: shell commands are validated at the schema layer
(``EventHookRequest.validate_action_safety``) against an allowlist
of safe prefixes and forbidden shell metacharacters (QA-160726 / DAWOS-02).
Execution uses ``create_subprocess_exec`` (no shell) for defense-in-depth.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import collections
import json
import logging
import shlex
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

#: Upper bound on retained event-history entries.  Prevents unbounded
#: in-memory growth on a long-running agent (DA-M11); mirrors the audit
#: ring buffer in :mod:`dawos_agent.middleware`.
_EVENT_LOG_MAXLEN = 1000

# In-memory hook store -------------------------------------------------------

_hooks: dict[str, dict] = {}
_event_log: collections.deque[dict] = collections.deque(maxlen=_EVENT_LOG_MAXLEN)

_VALID_EVENTS = frozenset(
    {
        "session-up",
        "session-down",
        "session-acct-start",
        "session-auth-fail",
        "shaper-change",
        "config-reload",
    }
)


def list_hooks() -> list[dict]:
    """Return all registered event hooks.

    Returns:
        A list of dicts with ``name``, ``event``, ``action``,
        ``enabled``, and ``fire_count`` for each hook.
    """
    return [
        {
            "name": h["name"],
            "event": h["event"],
            "action": h["action"],
            "enabled": h["enabled"],
            "fire_count": h.get("fire_count", 0),
        }
        for h in _hooks.values()
    ]


def add_hook(
    name: str,
    event: str,
    action: str,
    *,
    enabled: bool = True,
) -> dict:
    """Register a new event hook.

    Args:
        name: Unique hook identifier.
        event: Event type (must be in ``_VALID_EVENTS``).
        action: URL (webhook) or shell command to execute.
        enabled: Whether the hook is active.

    Raises:
        ValueError: If *name* already exists or *event* is invalid.
    """
    if name in _hooks:
        raise ValueError(f"Hook '{name}' already exists")
    if event not in _VALID_EVENTS:
        raise ValueError(
            f"Invalid event '{event}'. Valid: {', '.join(sorted(_VALID_EVENTS))}",
        )

    hook: dict = {
        "name": name,
        "event": event,
        "action": action,
        "enabled": enabled,
        "fire_count": 0,
    }
    _hooks[name] = hook
    return hook


def remove_hook(name: str) -> None:
    """Remove an event hook by name.

    Args:
        name: The hook identifier to remove.

    Raises:
        KeyError: If no hook with *name* exists.
    """
    if name not in _hooks:
        raise KeyError(f"Hook '{name}' not found")
    del _hooks[name]


async def fire_event(event: str, payload: dict | None = None) -> dict:
    """Fire an event and execute all matching enabled hooks.

    Hooks whose ``action`` starts with ``http://`` or ``https://`` are
    dispatched as webhook POSTs; all others are executed as shell commands.

    Args:
        event: The event type to fire (must be in ``_VALID_EVENTS``).
        payload: Optional context data associated with the event.

    Returns:
        A summary dict with ``event``, ``payload``, ``hooks_fired``,
        ``results``, and ``timestamp``.

    Raises:
        ValueError: If *event* is not a recognised event type.
    """
    if event not in _VALID_EVENTS:
        raise ValueError(f"Invalid event '{event}'")

    matching = [h for h in _hooks.values() if h["event"] == event and h["enabled"]]
    results: list[dict] = []

    for hook in matching:
        action = hook["action"]
        result: dict = {"hook": hook["name"], "action": action, "success": False}

        try:
            if action.startswith(("http://", "https://")):
                # Webhook — fire actual HTTP POST (DA-M10).
                result["type"] = "webhook"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    body = json.dumps(
                        {
                            "event": event,
                            "hook": hook["name"],
                            "payload": payload or {},
                        },
                        default=str,
                    )
                    resp = await client.post(
                        action,
                        content=body,
                        headers={"Content-Type": "application/json"},
                    )
                    result["success"] = resp.status_code < 400
                    result["status_code"] = resp.status_code
                log.info(
                    "Webhook fired: %s → %s (status=%d)",
                    hook["name"],
                    action,
                    resp.status_code,
                )
            else:
                # Shell command — exec without shell (QA-160726 / DAWOS-02)
                args = shlex.split(action)
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _stderr = await proc.communicate()
                result["type"] = "command"
                result["output"] = stdout.decode().strip()
                result["success"] = proc.returncode == 0
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
            log.warning("Hook %s failed: %s", hook["name"], exc)

        hook["fire_count"] = hook.get("fire_count", 0) + 1
        results.append(result)

    entry = {
        "event": event,
        "payload": payload or {},
        "hooks_fired": len(results),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _event_log.append(entry)

    return entry


def event_history(limit: int = 50) -> list[dict]:
    """Return the most recent event log entries.

    Args:
        limit: Maximum number of entries to return (default 50).

    Returns:
        A list of event log dicts, newest first.
    """
    return list(reversed(list(_event_log)[-limit:]))


def clear_history() -> int:
    """Clear the in-memory event history.

    Returns:
        The number of entries that were removed.
    """
    count = len(_event_log)
    _event_log.clear()
    return count
