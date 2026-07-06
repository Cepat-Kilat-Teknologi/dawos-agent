"""Tests for routers/flow_router.py — Flow accounting endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /flow/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_status(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_status",
        new_callable=AsyncMock,
        return_value={"active": True, "daemon": "pmacctd", "raw_output": "active"},
    ):
        resp = await client.get("/api/v1/flow/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert resp.json()["daemon"] == "pmacctd"


@pytest.mark.asyncio
async def test_flow_status_error(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/flow/status", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_flow_status_no_auth(client):
    resp = await client.get("/api/v1/flow/status")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /flow/collectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_collectors(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_collectors",
        new_callable=AsyncMock,
        return_value={
            "count": 1,
            "collectors": [
                {
                    "host": "10.0.0.1",
                    "port": 9995,
                    "protocol": "netflow",
                    "source": "softflowd",
                },
            ],
        },
    ):
        resp = await client.get("/api/v1/flow/collectors", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_flow_collectors_error(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_collectors",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/flow/collectors", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /flow/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_stats(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_stats",
        new_callable=AsyncMock,
        return_value={
            "flows_exported": 100,
            "packets_processed": 5000,
            "raw_output": "stats",
        },
    ):
        resp = await client.get("/api/v1/flow/stats", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["flows_exported"] == 100


@pytest.mark.asyncio
async def test_flow_stats_error(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_stats",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/flow/stats", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /flow/restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_restart(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_restart",
        new_callable=AsyncMock,
        return_value={"success": True, "daemon": "softflowd", "message": "restarted"},
    ):
        resp = await client.post("/api/v1/flow/restart", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_flow_restart_error(client, headers):
    with patch(
        "dawos_agent.routers.flow_router.flow_accounting.flow_restart",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/flow/restart", headers=headers)
    assert resp.status_code == 500
