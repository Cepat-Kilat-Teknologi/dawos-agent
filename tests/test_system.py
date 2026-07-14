"""Tests for system info, metrics, and extended stats endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_system_info(client, headers):
    resp = await client.get("/api/v1/system/info", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "hostname" in data
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "interfaces" in data
    assert data["cpu"]["count"] > 0
    assert data["memory"]["total_mb"] > 0


@pytest.mark.asyncio
async def test_system_metrics(client, headers):
    resp = await client.get("/api/v1/system/metrics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "timestamp" in data


# ---------------------------------------------------------------------------
# GET /api/v1/system/stats — extended accel-ppp statistics
# ---------------------------------------------------------------------------

_MOCK_EXTENDED_STATS = {
    "uptime": "2.12:58:33",
    "cpu": "3",
    "memory": {"rss_kb": 7652, "virt_kb": 176260},
    "core": {
        "mempool_allocated": 279302,
        "mempool_available": 197230,
        "thread_count": 2,
        "thread_active": 1,
        "context_count": 18,
        "context_sleeping": 0,
        "context_pending": 0,
        "md_handler_count": 23,
        "md_handler_pending": 0,
        "timer_count": 18,
        "timer_pending": 0,
    },
    "sessions": {"starting": 0, "active": 9, "finishing": 0},
    "pppoe": {
        "starting": 0,
        "active": 9,
        "delayed_pado": 0,
        "recv_padi": 21553,
        "drop_padi": 0,
        "sent_pado": 21553,
        "recv_padr": 20041,
        "recv_padr_dup": 0,
        "sent_pads": 20041,
        "filtered": 0,
    },
    "radius": [
        {
            "server_id": "3",
            "server_address": "10.100.0.253",
            "state": "active",
            "fail_count": 0,
            "request_count": 0,
            "queue_length": 0,
            "auth_sent": 454,
            "auth_lost_total": 414,
            "auth_lost_5m": 0,
            "auth_lost_1m": 0,
            "auth_avg_query_time_5m": 0,
            "auth_avg_query_time_1m": 0,
            "acct_sent": 124,
            "acct_lost_total": 53,
            "acct_lost_5m": 0,
            "acct_lost_1m": 0,
            "acct_avg_query_time_5m": 0,
            "acct_avg_query_time_1m": 0,
            "interim_sent": 2561,
            "interim_lost_total": 64,
            "interim_lost_5m": 0,
            "interim_lost_1m": 0,
            "interim_avg_query_time_5m": 33,
            "interim_avg_query_time_1m": 32,
        }
    ],
}


@pytest.mark.asyncio
async def test_system_stats(client, headers):
    """GET /api/v1/system/stats returns full accel-ppp stats."""
    with patch(
        "dawos_agent.routers.system.accel.show_stat_extended",
        new_callable=AsyncMock,
        return_value=_MOCK_EXTENDED_STATS,
    ):
        resp = await client.get("/api/v1/system/stats", headers=headers)

    assert resp.status_code == 200
    data = resp.json()

    assert data["uptime"] == "2.12:58:33"
    assert data["cpu"] == "3"
    assert data["memory"]["rss_kb"] == 7652
    assert data["memory"]["virt_kb"] == 176260
    assert data["core"]["mempool_allocated"] == 279302
    assert data["core"]["thread_count"] == 2
    assert data["sessions"]["active"] == 9
    assert data["pppoe"]["recv_padi"] == 21553
    assert data["pppoe"]["recv_padr"] == 20041
    assert len(data["radius"]) == 1
    assert data["radius"][0]["server_address"] == "10.100.0.253"
    assert data["radius"][0]["auth_sent"] == 454
    assert data["radius"][0]["interim_avg_query_time_5m"] == 33


@pytest.mark.asyncio
async def test_system_stats_error(client, headers):
    """GET /api/v1/system/stats returns 500 on accel-cmd failure."""
    with patch(
        "dawos_agent.routers.system.accel.show_stat_extended",
        new_callable=AsyncMock,
        side_effect=RuntimeError("conn refused"),
    ):
        resp = await client.get("/api/v1/system/stats", headers=headers)

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


@pytest.mark.asyncio
async def test_system_stats_empty(client, headers):
    """GET /api/v1/system/stats with empty stat output returns defaults."""
    empty_stats = {
        "uptime": "",
        "cpu": "0",
        "memory": {"rss_kb": 0, "virt_kb": 0},
        "core": {},
        "sessions": {"starting": 0, "active": 0, "finishing": 0},
        "pppoe": {},
        "radius": [],
    }
    with patch(
        "dawos_agent.routers.system.accel.show_stat_extended",
        new_callable=AsyncMock,
        return_value=empty_stats,
    ):
        resp = await client.get("/api/v1/system/stats", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["uptime"] == ""
    assert data["cpu"] == "0"
    assert data["memory"]["rss_kb"] == 0
    assert data["sessions"]["active"] == 0
    assert data["radius"] == []


@pytest.mark.asyncio
async def test_system_stats_auth_required(client, bad_headers):
    """GET /api/v1/system/stats requires valid API key."""
    resp = await client.get("/api/v1/system/stats", headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Extended stats Pydantic models
# ---------------------------------------------------------------------------


def test_extended_stats_model_defaults():
    """ExtendedStatsResponse defaults are safe when constructed empty."""
    from dawos_agent.models.schemas import ExtendedStatsResponse

    stats = ExtendedStatsResponse()
    assert stats.uptime == ""
    assert stats.cpu == "0"
    assert stats.memory.rss_kb == 0
    assert stats.memory.virt_kb == 0
    assert stats.core.mempool_allocated == 0
    assert stats.sessions.starting == 0
    assert stats.pppoe.starting == 0
    assert stats.radius == []


def test_core_stats_model():
    """CoreStats model accepts all fields."""
    from dawos_agent.models.schemas import CoreStats

    core = CoreStats(
        mempool_allocated=100,
        mempool_available=50,
        thread_count=4,
        thread_active=2,
        context_count=10,
        context_sleeping=3,
        context_pending=1,
        md_handler_count=5,
        md_handler_pending=0,
        timer_count=8,
        timer_pending=2,
    )
    assert core.mempool_allocated == 100
    assert core.thread_count == 4
    assert core.timer_pending == 2


def test_pppoe_stats_model():
    """PppoeStats model accepts all fields."""
    from dawos_agent.models.schemas import PppoeStats

    pppoe = PppoeStats(
        starting=1,
        active=10,
        delayed_pado=2,
        recv_padi=1000,
        drop_padi=5,
        sent_pado=995,
        recv_padr=990,
        recv_padr_dup=3,
        sent_pads=987,
        filtered=2,
    )
    assert pppoe.recv_padi == 1000
    assert pppoe.recv_padr_dup == 3
    assert pppoe.filtered == 2


def test_radius_server_stats_model():
    """RadiusServerStats model accepts all fields."""
    from dawos_agent.models.schemas import RadiusServerStats

    rad = RadiusServerStats(
        server_id="1",
        server_address="10.0.0.1",
        state="active",
        fail_count=0,
        request_count=5,
        queue_length=0,
        auth_sent=100,
        auth_lost_total=2,
        auth_lost_5m=0,
        auth_lost_1m=0,
        auth_avg_query_time_5m=15,
        auth_avg_query_time_1m=12,
        acct_sent=50,
        acct_lost_total=1,
        acct_lost_5m=0,
        acct_lost_1m=0,
        acct_avg_query_time_5m=10,
        acct_avg_query_time_1m=8,
        interim_sent=200,
        interim_lost_total=5,
        interim_lost_5m=1,
        interim_lost_1m=0,
        interim_avg_query_time_5m=20,
        interim_avg_query_time_1m=18,
    )
    assert rad.server_id == "1"
    assert rad.auth_sent == 100
    assert rad.interim_avg_query_time_1m == 18


def test_memory_stats_model():
    """MemoryStats model accepts rss and virt."""
    from dawos_agent.models.schemas import MemoryStats

    mem = MemoryStats(rss_kb=7652, virt_kb=176260)
    assert mem.rss_kb == 7652
    assert mem.virt_kb == 176260


def test_session_section_stats_model():
    """SessionSectionStats model defaults and accepts values."""
    from dawos_agent.models.schemas import SessionSectionStats

    s = SessionSectionStats()
    assert s.starting == 0
    assert s.active == 0
    assert s.finishing == 0

    s2 = SessionSectionStats(starting=1, active=50, finishing=2)
    assert s2.active == 50
