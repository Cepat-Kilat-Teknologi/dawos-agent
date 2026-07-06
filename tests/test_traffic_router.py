"""Tests for routers/traffic.py — endpoint tests with mocked services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# SSE streams
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_user_traffic(client, headers):
    async def mock_gen(username, interval=2.0):
        yield 'data: {"username": "user1", "download_mbps": 5.0}\n\n'

    with patch(
        "dawos_agent.routers.traffic.traffic.user_traffic_events",
        side_effect=mock_gen,
    ):
        resp = await client.get(
            "/api/v1/traffic/stream/user1",
            headers=headers,
        )

    assert resp.status_code == 200
    assert "download_mbps" in resp.text


@pytest.mark.asyncio
async def test_stream_aggregate_traffic(client, headers):
    async def mock_gen(interval=2.0):
        yield 'data: {"session_count": 2}\n\n'

    with patch(
        "dawos_agent.routers.traffic.traffic.aggregate_traffic_events",
        side_effect=mock_gen,
    ):
        resp = await client.get(
            "/api/v1/traffic/stream",
            headers=headers,
        )

    assert resp.status_code == 200
    assert "session_count" in resp.text


# ---------------------------------------------------------------------------
# Queue stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_stats(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.get_queue_stats",
        new_callable=AsyncMock,
        return_value={
            "username": "user1",
            "ifname": "ppp0",
            "qdisc": "fq_codel",
            "classes": "",
            "filters": "",
        },
    ):
        resp = await client.get(
            "/api/v1/traffic/queue/user1",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ifname"] == "ppp0"


@pytest.mark.asyncio
async def test_queue_stats_not_found(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.get_queue_stats",
        new_callable=AsyncMock,
        side_effect=ValueError("No live session"),
    ):
        resp = await client.get(
            "/api/v1/traffic/queue/offline",
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_queue_stats_error(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.get_queue_stats",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/traffic/queue/user1",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Ratelimit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_ratelimit(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.change_ratelimit",
        new_callable=AsyncMock,
        return_value="Shaper changed",
    ):
        resp = await client.post(
            "/api/v1/traffic/ratelimit/user1",
            headers=headers,
            json={"rate": "5M/20M"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["rate"] == "5M/20M"


@pytest.mark.asyncio
async def test_change_ratelimit_not_found(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.change_ratelimit",
        new_callable=AsyncMock,
        side_effect=ValueError("No live session"),
    ):
        resp = await client.post(
            "/api/v1/traffic/ratelimit/offline",
            headers=headers,
            json={"rate": "5M/20M"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_change_ratelimit_error(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.change_ratelimit",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/traffic/ratelimit/user1",
            headers=headers,
            json={"rate": "5M/20M"},
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_restore_ratelimit(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.restore_ratelimit",
        new_callable=AsyncMock,
        return_value="Shaper restored",
    ):
        resp = await client.delete(
            "/api/v1/traffic/ratelimit/user1",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["rate"] == "restored"


@pytest.mark.asyncio
async def test_restore_ratelimit_not_found(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.restore_ratelimit",
        new_callable=AsyncMock,
        side_effect=ValueError("No live session"),
    ):
        resp = await client.delete(
            "/api/v1/traffic/ratelimit/offline",
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_restore_ratelimit_error(client, headers):
    with patch(
        "dawos_agent.routers.traffic.traffic.restore_ratelimit",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.delete(
            "/api/v1/traffic/ratelimit/user1",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_traffic_requires_auth(client, bad_headers):
    resp = await client.get(
        "/api/v1/traffic/queue/user1",
        headers=bad_headers,
    )
    assert resp.status_code == 401
