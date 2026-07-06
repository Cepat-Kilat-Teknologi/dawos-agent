"""Tests for routers/event_router.py — Event handler endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import event_handler


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Reset in-memory stores before each test."""
    event_handler._hooks.clear()
    event_handler._event_log.clear()
    yield
    event_handler._hooks.clear()
    event_handler._event_log.clear()


# ---------------------------------------------------------------------------
# GET /events/hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_hooks(client, headers):
    resp = await client.get("/api/v1/events/hooks", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_list_hooks_no_auth(client):
    resp = await client.get("/api/v1/events/hooks")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /events/hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_hook(client, headers):
    resp = await client.post(
        "/api/v1/events/hooks",
        headers=headers,
        json={
            "name": "test-hook",
            "event": "session-up",
            "action": "https://example.com/hook",
            "enabled": True,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "test-hook"


@pytest.mark.asyncio
async def test_add_hook_duplicate(client, headers):
    event_handler.add_hook("dup", "session-up", "cmd")
    resp = await client.post(
        "/api/v1/events/hooks",
        headers=headers,
        json={"name": "dup", "event": "session-down", "action": "cmd2"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_hook_invalid_event(client, headers):
    resp = await client.post(
        "/api/v1/events/hooks",
        headers=headers,
        json={"name": "bad", "event": "bogus", "action": "cmd"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /events/hooks/{name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_hook(client, headers):
    event_handler.add_hook("rm1", "session-up", "cmd")
    resp = await client.delete("/api/v1/events/hooks/rm1", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_hook_not_found(client, headers):
    resp = await client.delete("/api/v1/events/hooks/nope", headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /events/fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_event(client, headers):
    event_handler.add_hook("wh1", "session-up", "https://example.com/hook")
    resp = await client.post(
        "/api/v1/events/fire",
        headers=headers,
        json={"event": "session-up", "payload": {"user": "test"}},
    )
    assert resp.status_code == 200
    assert resp.json()["hooks_fired"] == 1


@pytest.mark.asyncio
async def test_fire_event_invalid(client, headers):
    resp = await client.post(
        "/api/v1/events/fire",
        headers=headers,
        json={"event": "bogus-event", "payload": {}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fire_event_generic_error(client, headers):
    with patch(
        "dawos_agent.routers.event_router.event_handler.fire_event",
        new_callable=AsyncMock,
        side_effect=RuntimeError("unexpected"),
    ):
        resp = await client.post(
            "/api/v1/events/fire",
            headers=headers,
            json={"event": "session-up", "payload": {}},
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /events/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_history(client, headers):
    event_handler._event_log.append({"event": "session-up", "hooks_fired": 0})
    resp = await client.get("/api/v1/events/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


# ---------------------------------------------------------------------------
# DELETE /events/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_history(client, headers):
    event_handler._event_log.extend([{"a": 1}, {"b": 2}])
    resp = await client.delete("/api/v1/events/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["cleared"] == 2


@pytest.mark.asyncio
async def test_clear_history_empty(client, headers):
    resp = await client.delete("/api/v1/events/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["cleared"] == 0
