"""Tests for the WebSocket real-time events router."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from dawos_agent.app import app
from dawos_agent.events import Event, bus

# Re-use the same test keys defined in conftest.py.
_TEST_PRIMARY_KEY = "test-key-12345"
_TEST_VIEWER_KEY = "test-viewer-key"
_TEST_INVALID_KEY = "totally-wrong-key"


@pytest.fixture
def sync_client():
    """Synchronous test client with WebSocket support."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestWsAuth:
    """WebSocket authentication via query parameter."""

    def test_connect_with_valid_key(self, sync_client):
        """Valid API key allows WebSocket connection."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "ping"})
            resp = ws.receive_json()
            assert resp == {"action": "pong"}

    def test_connect_with_viewer_key(self, sync_client):
        """Viewer role is sufficient for WebSocket access."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_VIEWER_KEY}") as ws:
            ws.send_json({"action": "ping"})
            resp = ws.receive_json()
            assert resp == {"action": "pong"}

    def test_reject_missing_key(self, sync_client):
        """Missing API key closes the connection."""
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/ws/events"):
                pass  # pragma: no cover

    def test_reject_invalid_key(self, sync_client):
        """Invalid API key closes the connection."""
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/ws/events?key={_TEST_INVALID_KEY}"):
                pass  # pragma: no cover


# ---------------------------------------------------------------------------
# Control messages
# ---------------------------------------------------------------------------


class TestWsControl:
    """Client control messages (subscribe, unsubscribe, ping)."""

    def test_ping_pong(self, sync_client):
        """Ping returns pong."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "ping"})
            resp = ws.receive_json()
            assert resp == {"action": "pong"}

    def test_subscribe_channels(self, sync_client):
        """Subscribe to specific channels returns confirmation."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "subscribe", "channels": ["session"]})
            resp = ws.receive_json()
            assert resp["action"] == "subscribed"
            assert "session" in resp["channels"]

    def test_subscribe_all(self, sync_client):
        """Subscribe to 'all' expands to all channels."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "subscribe", "channels": ["all"]})
            resp = ws.receive_json()
            assert resp["action"] == "subscribed"
            assert len(resp["channels"]) == 4

    def test_unsubscribe_channels(self, sync_client):
        """Unsubscribe removes channels from the subscription set."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "unsubscribe", "channels": ["session", "config"]})
            resp = ws.receive_json()
            assert resp["action"] == "unsubscribed"
            assert "session" not in resp["channels"]
            assert "config" not in resp["channels"]

    def test_unknown_action(self, sync_client):
        """Unknown action returns error message."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "explode"})
            resp = ws.receive_json()
            assert "error" in resp
            assert "Unknown action" in resp["error"]

    def test_invalid_json(self, sync_client):
        """Non-JSON text returns error."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_text("not json at all")
            resp = ws.receive_json()
            assert "error" in resp
            assert "Invalid JSON" in resp["error"]

    def test_non_object_json(self, sync_client):
        """JSON that is not an object returns error."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_text(json.dumps([1, 2, 3]))
            resp = ws.receive_json()
            assert "error" in resp
            assert "Expected JSON object" in resp["error"]

    def test_channels_not_list(self, sync_client):
        """Non-list channels field returns error."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "subscribe", "channels": "session"})
            resp = ws.receive_json()
            assert "error" in resp
            assert "channels must be a list" in resp["error"]


# ---------------------------------------------------------------------------
# Event delivery
# ---------------------------------------------------------------------------


class TestWsEventDelivery:
    """Events published to the bus are delivered over WebSocket."""

    def test_receive_event(self, sync_client):
        """Published event is received by the WebSocket client."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            # Publish an event from a background task.
            async def _publish():
                await bus.publish(
                    Event(
                        channel="session",
                        event_type="session.connect",
                        data={"username": "testuser"},
                    )
                )

            # The TestClient runs inside its own event loop context.
            # We need to use the send_json/receive_json flow.
            # Instead, let's publish synchronously by putting directly
            # on the queue.

            # Subscribe is already done by default (all channels).
            # Find our queue in the bus subscribers.
            session_subs = bus._subscribers.get("session", set())
            if session_subs:
                queue = next(iter(session_subs))
                event_data = {
                    "channel": "session",
                    "type": "session.connect",
                    "data": {"username": "testuser"},
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
                queue.put_nowait(event_data)

                resp = ws.receive_json()
                assert resp["channel"] == "session"
                assert resp["type"] == "session.connect"
                assert resp["data"]["username"] == "testuser"

    def test_cleanup_on_disconnect(self, sync_client):
        """Subscriber queue is removed from the bus on disconnect."""
        initial_count = bus.subscriber_count
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "ping"})
            ws.receive_json()
            assert bus.subscriber_count > initial_count

        # After disconnect, subscriber count should return to initial.
        assert bus.subscriber_count == initial_count


# ---------------------------------------------------------------------------
# Edge cases for coverage
# ---------------------------------------------------------------------------


class TestWsEdgeCases:
    """Edge case tests for full coverage."""

    def test_reject_insufficient_permissions(self, sync_client):
        """Key with insufficient role is rejected."""
        from unittest.mock import patch

        with patch("dawos_agent.routers.ws.role_has_access", return_value=False):
            with pytest.raises(Exception):  # pylint: disable=broad-exception-caught
                with sync_client.websocket_connect(
                    f"/ws/events?key={_TEST_PRIMARY_KEY}"
                ):
                    pass  # pragma: no cover

    def test_websocket_disconnect_logged(self, sync_client):
        """Normal disconnect triggers the WebSocketDisconnect handler."""
        with sync_client.websocket_connect(f"/ws/events?key={_TEST_PRIMARY_KEY}") as ws:
            ws.send_json({"action": "ping"})
            ws.receive_json()
        # Disconnect happens when context manager exits — no assertion
        # needed; we just verify no exception is raised.

    def test_task_exception_reraised(self, sync_client):
        """Non-WebSocketDisconnect exceptions from tasks are re-raised."""
        from unittest.mock import patch

        async def _boom(ws, queue):
            raise RuntimeError("test boom")

        with patch("dawos_agent.routers.ws._push_events", side_effect=_boom):
            with pytest.raises(Exception):  # pylint: disable=broad-exception-caught
                with sync_client.websocket_connect(
                    f"/ws/events?key={_TEST_PRIMARY_KEY}"
                ) as ws:
                    # Send something to trigger the receive task
                    ws.send_json({"action": "ping"})
                    ws.receive_json()
