"""Tests for routers/session_history_router.py — session history endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /sessions/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_history(client, headers):
    mock_data = {
        "records": [
            {
                "id": 1,
                "snapshot_at": "2026-01-01T00:00:00",
                "username": "user1",
                "ip": "10.0.0.1",
                "sid": "s1",
                "ifname": "ppp0",
                "calling_sid": "AA:BB:CC:DD:EE:FF",
                "state": "active",
                "uptime": "01:00:00",
                "rx_bytes": "1000",
                "tx_bytes": "2000",
            }
        ],
        "total": 1,
        "limit": 100,
        "offset": 0,
    }
    with patch(
        "dawos_agent.routers.session_history_router.session_history.query_history",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        resp = await client.get("/api/v1/sessions/history", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["records"]) == 1
    assert body["records"][0]["username"] == "user1"


@pytest.mark.asyncio
async def test_get_history_with_filters(client, headers):
    mock_data = {"records": [], "total": 0, "limit": 50, "offset": 0}
    with patch(
        "dawos_agent.routers.session_history_router.session_history.query_history",
        new_callable=AsyncMock,
        return_value=mock_data,
    ) as mock_query:
        resp = await client.get(
            "/api/v1/sessions/history?username=alice&ip=10.0.0.1"
            "&start=2026-01-01&end=2026-12-31&limit=50&offset=10",
            headers=headers,
        )
    assert resp.status_code == 200
    mock_query.assert_called_once_with(
        username="alice",
        ip="10.0.0.1",
        start="2026-01-01",
        end="2026-12-31",
        limit=50,
        offset=10,
    )


@pytest.mark.asyncio
async def test_get_history_error(client, headers):
    with patch(
        "dawos_agent.routers.session_history_router.session_history.query_history",
        new_callable=AsyncMock,
        side_effect=Exception("db fail"),
    ):
        resp = await client.get("/api/v1/sessions/history", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /sessions/history/snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_snapshot(client, headers):
    mock_data = {
        "success": True,
        "captured": 5,
        "snapshot_at": "2026-01-01T12:00:00+00:00",
    }
    with patch(
        "dawos_agent.routers.session_history_router.session_history.snapshot_sessions",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        resp = await client.post("/api/v1/sessions/history/snapshot", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["captured"] == 5


@pytest.mark.asyncio
async def test_take_snapshot_error(client, headers):
    with patch(
        "dawos_agent.routers.session_history_router.session_history.snapshot_sessions",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/sessions/history/snapshot", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /sessions/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge(client, headers):
    with patch(
        "dawos_agent.routers.session_history_router.session_history.purge_history",
        new_callable=AsyncMock,
        return_value=10,
    ):
        resp = await client.delete(
            "/api/v1/sessions/history?before=2026-01-01T00:00:00",
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 10


@pytest.mark.asyncio
async def test_purge_error(client, headers):
    with patch(
        "dawos_agent.routers.session_history_router.session_history.purge_history",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.delete(
            "/api/v1/sessions/history?before=2026-01-01T00:00:00",
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /sessions/history/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats(client, headers):
    mock_data = {
        "total_records": 100,
        "unique_users": 25,
        "oldest_snapshot": "2026-01-01T00:00:00",
        "newest_snapshot": "2026-06-01T00:00:00",
        "db_size_bytes": 4096,
    }
    with patch(
        "dawos_agent.routers.session_history_router.session_history.history_stats",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        resp = await client.get("/api/v1/sessions/history/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_records"] == 100
    assert body["unique_users"] == 25


@pytest.mark.asyncio
async def test_get_stats_error(client, headers):
    with patch(
        "dawos_agent.routers.session_history_router.session_history.history_stats",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/sessions/history/stats", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_get_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/sessions/history", headers=bad_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_history_snapshot_requires_auth(client, bad_headers):
    resp = await client.post("/api/v1/sessions/history/snapshot", headers=bad_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_history_purge_requires_auth(client, bad_headers):
    resp = await client.delete(
        "/api/v1/sessions/history?before=2026-01-01", headers=bad_headers
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_history_stats_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/sessions/history/stats", headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Model smoke tests
# ---------------------------------------------------------------------------


def test_session_history_record_defaults():
    from dawos_agent.models.schemas import SessionHistoryRecord

    obj = SessionHistoryRecord()
    assert obj.id == 0
    assert obj.username == ""
    assert obj.snapshot_at == ""


def test_session_history_response_defaults():
    from dawos_agent.models.schemas import SessionHistoryResponse

    obj = SessionHistoryResponse()
    assert obj.records == []
    assert obj.total == 0


def test_session_snapshot_result_defaults():
    from dawos_agent.models.schemas import SessionSnapshotResult

    obj = SessionSnapshotResult()
    assert obj.success is True
    assert obj.captured == 0


def test_session_history_stats_defaults():
    from dawos_agent.models.schemas import SessionHistoryStatsResponse

    obj = SessionHistoryStatsResponse()
    assert obj.total_records == 0
    assert obj.db_size_bytes == 0
