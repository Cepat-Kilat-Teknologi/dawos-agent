"""Tests for the in-memory event bus."""

from __future__ import annotations

import pytest

from dawos_agent.events import CHANNELS, Event, EventBus, bus

# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


class TestEvent:
    """Tests for the Event dataclass."""

    def test_to_dict(self):
        """Event serializes to a dictionary with all fields."""
        ev = Event(
            channel="session",
            event_type="session.connect",
            data={"username": "user1"},
            timestamp="2026-01-01T00:00:00+00:00",
        )
        result = ev.to_dict()
        assert result["channel"] == "session"
        assert result["type"] == "session.connect"
        assert result["data"] == {"username": "user1"}
        assert result["timestamp"] == "2026-01-01T00:00:00+00:00"

    def test_auto_timestamp(self):
        """Event generates a timestamp when none is provided."""
        ev = Event(channel="config", event_type="config.write")
        assert ev.timestamp
        assert "T" in ev.timestamp  # ISO format

    def test_explicit_timestamp_preserved(self):
        """Explicitly provided timestamp is not overwritten."""
        ts = "2025-12-25T00:00:00+00:00"
        ev = Event(channel="system", event_type="start", timestamp=ts)
        assert ev.timestamp == ts

    def test_default_data(self):
        """Event data defaults to an empty dict."""
        ev = Event(channel="audit", event_type="request")
        assert ev.data == {}


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class TestEventBus:
    """Tests for the EventBus pub/sub system."""

    def test_subscribe_all(self):
        """Subscribing to 'all' registers on every channel."""
        eb = EventBus()
        queue = eb.subscribe({"all"})
        assert eb.subscriber_count == 1
        for ch in CHANNELS:
            assert queue in eb._subscribers.get(ch, set())

    def test_subscribe_none_means_all(self):
        """Passing None subscribes to all channels."""
        eb = EventBus()
        queue = eb.subscribe(None)
        assert eb.subscriber_count == 1
        for ch in CHANNELS:
            assert queue in eb._subscribers.get(ch, set())

    def test_subscribe_specific_channels(self):
        """Subscribing to specific channels only registers those."""
        eb = EventBus()
        queue = eb.subscribe({"session", "config"})
        assert queue in eb._subscribers.get("session", set())
        assert queue in eb._subscribers.get("config", set())
        assert queue not in eb._subscribers.get("audit", set())
        assert queue not in eb._subscribers.get("system", set())

    def test_unsubscribe(self):
        """Unsubscribing removes the queue from all channels."""
        eb = EventBus()
        queue = eb.subscribe({"all"})
        assert eb.subscriber_count == 1
        eb.unsubscribe(queue)
        assert eb.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_publish_delivers(self):
        """Published events are delivered to matching subscribers."""
        eb = EventBus()
        queue = eb.subscribe({"session"})
        event = Event(channel="session", event_type="connect", data={"user": "x"})
        delivered = await eb.publish(event)
        assert delivered == 1
        msg = queue.get_nowait()
        assert msg["type"] == "connect"
        assert msg["data"] == {"user": "x"}

    @pytest.mark.asyncio
    async def test_publish_no_match(self):
        """Events on unsubscribed channels are not delivered."""
        eb = EventBus()
        queue = eb.subscribe({"session"})
        event = Event(channel="config", event_type="write")
        delivered = await eb.publish(event)
        assert delivered == 0
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_publish_full_queue_skipped(self):
        """Full queues are skipped without blocking the publisher."""
        eb = EventBus(max_queue=1)
        queue = eb.subscribe({"session"})

        # Fill the queue.
        event1 = Event(channel="session", event_type="first")
        await eb.publish(event1)

        # Second event should be dropped.
        event2 = Event(channel="session", event_type="second")
        delivered = await eb.publish(event2)
        assert delivered == 0

        # Only the first event is in the queue.
        msg = queue.get_nowait()
        assert msg["type"] == "first"

    @pytest.mark.asyncio
    async def test_publish_multiple_subscribers(self):
        """Events fan out to all matching subscribers."""
        eb = EventBus()
        q1 = eb.subscribe({"session"})
        q2 = eb.subscribe({"session"})
        event = Event(channel="session", event_type="connect")
        delivered = await eb.publish(event)
        assert delivered == 2
        assert not q1.empty()
        assert not q2.empty()

    def test_subscriber_count(self):
        """Subscriber count reflects unique queues."""
        eb = EventBus()
        eb.subscribe({"session", "config"})  # one queue, two channels
        eb.subscribe({"audit"})  # second queue
        assert eb.subscriber_count == 2


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestModuleSingleton:
    """Tests for the module-level bus instance."""

    def test_bus_is_event_bus(self):
        """The module-level bus is an EventBus instance."""
        assert isinstance(bus, EventBus)

    def test_channels_constant(self):
        """CHANNELS contains the expected event channel names."""
        assert {"session", "config", "audit", "system"} == CHANNELS
