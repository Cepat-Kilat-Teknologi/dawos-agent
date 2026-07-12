"""Tests for routers/conntrack_router.py — conntrack REST endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.get_config",
        return_value={
            "table_size": 262144,
            "current_count": 50000,
            "hash_size": 65536,
            "usage_percent": 19.1,
        },
    ):
        resp = await client.get("/api/v1/conntrack/config", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["table_size"] == 262144


@pytest.mark.asyncio
async def test_get_config_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.get_config",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/conntrack/config", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_table_size(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.set_table_size",
        return_value={
            "table_size": 500000,
            "current_count": 0,
            "hash_size": 0,
            "usage_percent": 0.0,
        },
    ):
        resp = await client.put(
            "/api/v1/conntrack/table-size",
            json={"size": 500000},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["table_size"] == 500000


@pytest.mark.asyncio
async def test_set_table_size_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.set_table_size",
        side_effect=Exception("fail"),
    ):
        resp = await client.put(
            "/api/v1/conntrack/table-size",
            json={"size": 500000},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeouts(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.get_timeouts",
        return_value={"tcp_timeout_established": 432000},
    ):
        resp = await client.get("/api/v1/conntrack/timeouts", headers=headers)
    assert resp.status_code == 200
    assert "tcp_timeout_established" in resp.json()["timeouts"]


@pytest.mark.asyncio
async def test_get_timeouts_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.get_timeouts",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/conntrack/timeouts", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_timeout(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.set_timeout",
        return_value={"tcp_timeout_established": 600},
    ):
        resp = await client.put(
            "/api/v1/conntrack/timeouts",
            json={"key": "tcp_timeout_established", "seconds": 600},
            headers=headers,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_set_timeout_bad_key(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.set_timeout",
        side_effect=ValueError("Unknown timeout key"),
    ):
        resp = await client.put(
            "/api/v1/conntrack/timeouts",
            json={"key": "bogus", "seconds": 60},
            headers=headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_timeout_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.set_timeout",
        side_effect=Exception("fail"),
    ):
        resp = await client.put(
            "/api/v1/conntrack/timeouts",
            json={"key": "tcp_timeout_established", "seconds": 60},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_helpers(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.list_helpers",
        return_value=[{"module": "nf_conntrack_ftp", "size": 20480, "used_by": 0}],
    ):
        resp = await client.get("/api/v1/conntrack/helpers", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_helpers_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.list_helpers",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/conntrack/helpers", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_profiles(client, headers):
    resp = await client.get("/api/v1/conntrack/profiles", headers=headers)
    assert resp.status_code == 200
    assert "default" in resp.json()["profiles"]


@pytest.mark.asyncio
async def test_apply_profile(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.apply_profile",
        return_value={"tcp_timeout_established": 86400},
    ):
        resp = await client.post(
            "/api/v1/conntrack/profiles/apply",
            json={"name": "gaming"},
            headers=headers,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_apply_profile_unknown(client, headers):
    resp = await client.post(
        "/api/v1/conntrack/profiles/apply",
        json={"name": "fake"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_apply_profile_service_valueerror(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.apply_profile",
        side_effect=ValueError("Unknown profile"),
    ):
        resp = await client.post(
            "/api/v1/conntrack/profiles/apply",
            json={"name": "default"},
            headers=headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_apply_profile_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.apply_profile",
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/conntrack/profiles/apply",
            json={"name": "default"},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conntrack_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/conntrack/config", headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Flush
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_table(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.flush_table",
        new_callable=AsyncMock,
        return_value={
            "success": True,
            "message": "Conntrack table flushed",
            "entries_before": 2500,
        },
    ):
        resp = await client.post("/api/v1/conntrack/flush", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["entries_before"] == 2500


@pytest.mark.asyncio
async def test_flush_table_error(client, headers):
    with patch(
        "dawos_agent.routers.conntrack_router.conntrack.flush_table",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Failed to flush"),
    ):
        resp = await client.post("/api/v1/conntrack/flush", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_flush_table_requires_auth(client, bad_headers):
    resp = await client.post("/api/v1/conntrack/flush", headers=bad_headers)
    assert resp.status_code == 401
