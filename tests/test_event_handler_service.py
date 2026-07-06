"""Tests for services/event_handler.py — webhook/script triggers."""

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
# list_hooks
# ---------------------------------------------------------------------------


def test_list_hooks_empty():
    assert event_handler.list_hooks() == []


def test_list_hooks_with_data():
    event_handler.add_hook("h1", "session-up", "http://example.com/hook")
    hooks = event_handler.list_hooks()
    assert len(hooks) == 1
    assert hooks[0]["name"] == "h1"
    assert hooks[0]["event"] == "session-up"
    assert hooks[0]["fire_count"] == 0


# ---------------------------------------------------------------------------
# add_hook
# ---------------------------------------------------------------------------


def test_add_hook():
    hook = event_handler.add_hook("test", "session-down", "/usr/bin/notify.sh")
    assert hook["name"] == "test"
    assert hook["event"] == "session-down"
    assert hook["enabled"] is True


def test_add_hook_disabled():
    hook = event_handler.add_hook("d1", "config-reload", "cmd", enabled=False)
    assert hook["enabled"] is False


def test_add_hook_duplicate():
    event_handler.add_hook("dup", "session-up", "cmd1")
    with pytest.raises(ValueError, match="already exists"):
        event_handler.add_hook("dup", "session-down", "cmd2")


def test_add_hook_invalid_event():
    with pytest.raises(ValueError, match="Invalid event"):
        event_handler.add_hook("bad", "invalid-event", "cmd")


# ---------------------------------------------------------------------------
# remove_hook
# ---------------------------------------------------------------------------


def test_remove_hook():
    event_handler.add_hook("rm1", "session-up", "cmd")
    event_handler.remove_hook("rm1")
    assert event_handler.list_hooks() == []


def test_remove_hook_not_found():
    with pytest.raises(KeyError, match="not found"):
        event_handler.remove_hook("nonexistent")


# ---------------------------------------------------------------------------
# fire_event — webhook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_event_webhook():
    event_handler.add_hook("wh1", "session-up", "https://example.com/hook")
    result = await event_handler.fire_event("session-up", {"user": "test"})

    assert result["event"] == "session-up"
    assert result["hooks_fired"] == 1
    assert result["results"][0]["type"] == "webhook"
    assert result["results"][0]["success"] is True


# ---------------------------------------------------------------------------
# fire_event — command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_event_command():
    event_handler.add_hook("cmd1", "session-down", "echo hello")
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"hello\n", b""))
    proc.returncode = 0

    with patch(
        "dawos_agent.services.event_handler.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await event_handler.fire_event("session-down")

    assert result["hooks_fired"] == 1
    assert result["results"][0]["type"] == "command"
    assert result["results"][0]["success"] is True
    assert result["results"][0]["output"] == "hello"


@pytest.mark.asyncio
async def test_fire_event_command_failure():
    event_handler.add_hook("fail1", "shaper-change", "false")
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"error"))
    proc.returncode = 1

    with patch(
        "dawos_agent.services.event_handler.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await event_handler.fire_event("shaper-change")

    assert result["results"][0]["success"] is False


# ---------------------------------------------------------------------------
# fire_event — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_event_invalid_event():
    with pytest.raises(ValueError, match="Invalid event"):
        await event_handler.fire_event("bogus-event")


@pytest.mark.asyncio
async def test_fire_event_exception_in_hook():
    event_handler.add_hook("err1", "config-reload", "some-cmd")

    with patch(
        "dawos_agent.services.event_handler.asyncio.create_subprocess_shell",
        side_effect=OSError("exec failed"),
    ):
        result = await event_handler.fire_event("config-reload")

    assert result["hooks_fired"] == 1
    assert result["results"][0]["success"] is False
    assert "exec failed" in result["results"][0]["error"]


# ---------------------------------------------------------------------------
# fire_event — disabled hooks, no match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_event_disabled_hook():
    event_handler.add_hook("dis1", "session-up", "cmd", enabled=False)
    result = await event_handler.fire_event("session-up")
    assert result["hooks_fired"] == 0


@pytest.mark.asyncio
async def test_fire_event_no_matching():
    event_handler.add_hook("m1", "session-up", "cmd")
    result = await event_handler.fire_event("session-down")
    assert result["hooks_fired"] == 0


# ---------------------------------------------------------------------------
# fire_event — fire_count increments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_count_increments():
    event_handler.add_hook("fc1", "session-up", "https://example.com")
    await event_handler.fire_event("session-up")
    await event_handler.fire_event("session-up")

    hooks = event_handler.list_hooks()
    assert hooks[0]["fire_count"] == 2


# ---------------------------------------------------------------------------
# event_history / clear_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_history():
    event_handler.add_hook("h1", "session-up", "https://example.com")
    await event_handler.fire_event("session-up")
    await event_handler.fire_event("session-up")

    history = event_handler.event_history()
    assert len(history) == 2
    # Most recent first
    assert history[0]["event"] == "session-up"


@pytest.mark.asyncio
async def test_event_history_limit():
    event_handler.add_hook("h1", "session-up", "https://example.com")
    for _ in range(5):
        await event_handler.fire_event("session-up")

    history = event_handler.event_history(limit=2)
    assert len(history) == 2


def test_clear_history():
    event_handler._event_log.extend([{"a": 1}, {"b": 2}])
    count = event_handler.clear_history()
    assert count == 2
    assert event_handler.event_history() == []


def test_clear_history_empty():
    count = event_handler.clear_history()
    assert count == 0
