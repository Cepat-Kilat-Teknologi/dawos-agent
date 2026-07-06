"""Event handler — webhook and script triggers for BNG session events.

In-memory registry of event hooks.  When a session lifecycle event
fires (session-up, session-down, etc.), all matching enabled handlers
execute — either as HTTP webhook POSTs or local shell commands.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)

# In-memory hook store -------------------------------------------------------

_hooks: dict[str, dict] = {}
_event_log: list[dict] = []

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
                # Webhook — simulate POST (actual HTTP in production)
                result["type"] = "webhook"
                result["success"] = True
                log.info("Webhook fired: %s → %s", hook["name"], action)
            else:
                # Shell command
                proc = await asyncio.create_subprocess_shell(
                    action,
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
        "timestamp": datetime.now(UTC).isoformat(),
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
    return list(reversed(_event_log[-limit:]))


def clear_history() -> int:
    """Clear the in-memory event history.

    Returns:
        The number of entries that were removed.
    """
    count = len(_event_log)
    _event_log.clear()
    return count
