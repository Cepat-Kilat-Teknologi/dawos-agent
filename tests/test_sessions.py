"""Tests for session endpoints — mocked accel-cmd calls."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_sessions(client, headers):
    mock_sessions = [
        {"ifname": "ppp0", "username": "user1", "ip": "10.0.0.1", "state": "active"},
        {"ifname": "ppp1", "username": "user2", "ip": "10.0.0.2", "state": "active"},
    ]
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ):
        resp = await client.get("/api/v1/sessions", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["sessions"][0]["username"] == "user1"


@pytest.mark.asyncio
async def test_list_sessions_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        side_effect=RuntimeError("conn refused"),
    ):
        resp = await client.get("/api/v1/sessions", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_session_stats(client, headers):
    mock_stat = {
        "sessions": {"active": 10, "starting": 1, "finishing": 0},
        "cpu": "3",
        "uptime": "1:00:00",
    }
    mock_pool = {"used": "10", "total": "100", "available": "90"}

    with (
        patch(
            "dawos_agent.routers.sessions.accel.show_stat",
            new_callable=AsyncMock,
            return_value=mock_stat,
        ),
        patch(
            "dawos_agent.routers.sessions.accel.show_ippool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ),
    ):
        resp = await client.get("/api/v1/sessions/stats", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] == 10
    assert data["pool_used"] == "10"


@pytest.mark.asyncio
async def test_session_stats_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.show_stat",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/sessions/stats", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_find_session(client, headers):
    table = (
        " ifname | username | ip\n------+--------+-----\n ppp0 | testuser | 10.0.0.5\n"
    )
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=table,
    ):
        resp = await client.get("/api/v1/sessions/find/testuser", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_find_session_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/sessions/find/testuser", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_terminate_session_by_username(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.terminate_session",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/sessions/terminate", headers=headers, json={"username": "user1"}
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_terminate_session_by_ifname(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.terminate_session",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/sessions/terminate", headers=headers, json={"ifname": "ppp0"}
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_terminate_session_no_target(client, headers):
    resp = await client.post("/api/v1/sessions/terminate", headers=headers, json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_terminate_session_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.terminate_session",
        new_callable=AsyncMock,
        side_effect=RuntimeError("not found"),
    ):
        resp = await client.post(
            "/api/v1/sessions/terminate", headers=headers, json={"username": "x"}
        )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"
