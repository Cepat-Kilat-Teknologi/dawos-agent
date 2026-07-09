"""In-memory event bus for real-time broadcasting.

Provides a lightweight publish/subscribe mechanism using asyncio queues.
Each connected WebSocket client gets its own queue; published events are
fanned out to all subscribers matching the event channel.

Channels
--------
- ``session`` — PPPoE session lifecycle (connect, disconnect, change).
- ``config`` — Configuration mutations (write, rollback, checkpoint).
- ``audit`` — HTTP audit trail for mutating requests.
- ``system`` — Service-level events (start, stop, health change).

The ``all`` pseudo-channel receives every event regardless of origin.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

log = logging.getLogger(__name__)

#: Valid event channels.
CHANNELS = {"session", "config", "audit", "system"}


@dataclass
class Event:
    """A single bus event."""

    channel: str
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "channel": self.channel,
            "type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class EventBus:
    """Fan-out event dispatcher backed by per-subscriber asyncio queues.

    Thread-safe for publishing; subscribers must be managed from the
    same event loop.
    """

    def __init__(self, max_queue: int = 100) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._max_queue = max_queue

    def subscribe(
        self,
        channels: Optional[Set[str]] = None,
    ) -> asyncio.Queue:
        """Create a new subscription queue for the given channels.

        Args:
            channels: Set of channel names.  ``None`` or ``{"all"}``
                subscribes to every channel.

        Returns:
            An asyncio.Queue that will receive matching events.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        targets = channels if channels and "all" not in channels else CHANNELS
        for ch in targets:
            self._subscribers.setdefault(ch, set()).add(queue)
        return queue

    def add_to_channel(self, channel: str, queue: asyncio.Queue) -> None:
        """Add a queue to a specific channel's subscriber set.

        Args:
            channel: The channel name to subscribe to.
            queue: The subscriber queue to add.
        """
        self._subscribers.setdefault(channel, set()).add(queue)

    def remove_from_channel(self, channel: str, queue: asyncio.Queue) -> None:
        """Remove a queue from a specific channel's subscriber set.

        Args:
            channel: The channel name to unsubscribe from.
            queue: The subscriber queue to remove.
        """
        subs = self._subscribers.get(channel)
        if subs:
            subs.discard(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue from all channels."""
        for channel_subs in self._subscribers.values():
            channel_subs.discard(queue)

    async def publish(self, event: Event) -> int:
        """Broadcast an event to matching subscribers.

        Full queues are skipped (slow consumers lose events rather
        than blocking the publisher).

        Returns:
            Number of subscribers that received the event.
        """
        delivered = 0
        queues = self._subscribers.get(event.channel, set())
        payload = event.to_dict()
        for q in list(queues):
            try:
                q.put_nowait(payload)
                delivered += 1
            except asyncio.QueueFull:
                log.debug("Dropping event for slow subscriber on %s", event.channel)
        return delivered

    @property
    def subscriber_count(self) -> int:
        """Return total unique subscriber queues."""
        unique: Set[int] = set()
        for queues in self._subscribers.values():
            for q in queues:
                unique.add(id(q))
        return len(unique)


#: Module-level singleton — shared across the application.
bus = EventBus()
