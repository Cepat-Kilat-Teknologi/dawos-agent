"""Tests for services/session_control.py — granular session ops."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import session_control


def _mock_run_cmd(output: str = ""):
    return AsyncMock(return_value=output)


# ---------------------------------------------------------------------------
# session_by_sid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_by_sid_found():
    table = "sid | ifname | username\nabc123 | ppp0 | user1"
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd(table)),
        patch.object(
            session_control.accel,
            "parse_table",
            return_value=[{"sid": "abc123", "ifname": "ppp0", "username": "user1"}],
        ),
    ):
        result = await session_control.session_by_sid("abc123")

    assert result is not None
    assert result["sid"] == "abc123"


@pytest.mark.asyncio
async def test_session_by_sid_not_found():
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(session_control.accel, "parse_table", return_value=[]),
    ):
        result = await session_control.session_by_sid("nope")

    assert result is None


# ---------------------------------------------------------------------------
# session_by_ip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_by_ip_found():
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(
            session_control.accel,
            "parse_table",
            return_value=[{"ip": "10.0.0.5", "username": "user1"}],
        ),
    ):
        result = await session_control.session_by_ip("10.0.0.5")

    assert result is not None
    assert result["ip"] == "10.0.0.5"


@pytest.mark.asyncio
async def test_session_by_ip_not_found():
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(session_control.accel, "parse_table", return_value=[]),
    ):
        result = await session_control.session_by_ip("10.0.0.99")

    assert result is None


# ---------------------------------------------------------------------------
# session_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_snapshot():
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(
            session_control.accel,
            "parse_table",
            return_value=[{"username": "user1", "rx-bytes": "1000"}],
        ),
    ):
        result = await session_control.session_snapshot("user1")

    assert result["found"] is True
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_session_snapshot_not_found():
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(session_control.accel, "parse_table", return_value=[]),
    ):
        result = await session_control.session_snapshot("ghost")

    assert result["found"] is False
    assert result["count"] == 0


# ---------------------------------------------------------------------------
# restart_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_session_success():
    with (
        patch.object(
            session_control.accel,
            "ifname_of",
            AsyncMock(return_value="ppp0"),
        ),
        patch.object(
            session_control.accel,
            "terminate_session",
            AsyncMock(return_value="ok"),
        ),
    ):
        result = await session_control.restart_session("user1")

    assert result["success"] is True
    assert result["previous_interface"] == "ppp0"


@pytest.mark.asyncio
async def test_restart_session_not_found():
    with patch.object(
        session_control.accel,
        "ifname_of",
        AsyncMock(return_value=None),
    ):
        result = await session_control.restart_session("ghost")

    assert result["success"] is False


# ---------------------------------------------------------------------------
# drop_by_mac
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drop_by_mac_found():
    rows = [
        {
            "sid": "1",
            "ifname": "ppp0",
            "username": "u1",
            "calling-sid": "AA:BB:CC:DD:EE:FF",
        },
        {
            "sid": "2",
            "ifname": "ppp1",
            "username": "u2",
            "calling-sid": "11:22:33:44:55:66",
        },
    ]
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(session_control.accel, "parse_table", return_value=rows),
        patch.object(
            session_control.accel,
            "terminate_session",
            AsyncMock(return_value="ok"),
        ),
    ):
        result = await session_control.drop_by_mac("AA:BB:CC:DD:EE:FF")

    assert result["success"] is True
    assert result["dropped"] == 1


@pytest.mark.asyncio
async def test_drop_by_mac_not_found():
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(session_control.accel, "parse_table", return_value=[]),
    ):
        result = await session_control.drop_by_mac("00:00:00:00:00:00")

    assert result["success"] is False
    assert result["dropped"] == 0


@pytest.mark.asyncio
async def test_drop_by_mac_terminate_error():
    """Cover the except branch when terminate fails for one session."""
    rows = [
        {
            "sid": "1",
            "ifname": "ppp0",
            "username": "u1",
            "calling-sid": "AA:BB:CC:DD:EE:FF",
        },
    ]
    with (
        patch.object(session_control.accel, "run_cmd", _mock_run_cmd("")),
        patch.object(session_control.accel, "parse_table", return_value=rows),
        patch.object(
            session_control.accel,
            "terminate_session",
            AsyncMock(side_effect=RuntimeError("fail")),
        ),
    ):
        result = await session_control.drop_by_mac("AA:BB:CC:DD:EE:FF")

    # Still reports success because it attempted all targets
    assert result["dropped"] == 1
