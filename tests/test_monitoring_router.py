"""Tests for routers/monitoring_router.py — Monitoring endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /monitoring/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_status(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.monitoring_status",
        new_callable=AsyncMock,
        return_value={
            "exporters": [
                {"service": "node_exporter", "active": True, "port": 9100},
            ],
            "count": 1,
        },
    ):
        resp = await client.get("/api/v1/monitoring/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_monitoring_status_error(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.monitoring_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/monitoring/status", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_monitoring_status_no_auth(client):
    resp = await client.get("/api/v1/monitoring/status")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /monitoring/metrics/{service}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exporter_metrics(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.exporter_metrics",
        new_callable=AsyncMock,
        return_value={
            "service": "node_exporter",
            "available": True,
            "metrics": [{"name": "cpu", "value": "1.0"}],
            "raw_output": "ok",
        },
    ):
        resp = await client.get(
            "/api/v1/monitoring/metrics/node_exporter", headers=headers
        )
    assert resp.status_code == 200
    assert resp.json()["available"] is True


@pytest.mark.asyncio
async def test_exporter_metrics_error(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.exporter_metrics",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/monitoring/metrics/bad", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /monitoring/configure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_exporter(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.configure_exporter",
        new_callable=AsyncMock,
        return_value={
            "success": True,
            "service": "node_exporter",
            "enabled": True,
            "message": "enabled",
        },
    ):
        resp = await client.post(
            "/api/v1/monitoring/configure",
            headers=headers,
            json={"service": "node_exporter", "enable": True},
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_configure_exporter_error(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.configure_exporter",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/monitoring/configure",
            headers=headers,
            json={"service": "bad", "enable": True},
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /monitoring/restart/{service}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exporter_restart(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.exporter_restart",
        new_callable=AsyncMock,
        return_value={
            "success": True,
            "service": "node_exporter",
            "message": "restarted",
        },
    ):
        resp = await client.post(
            "/api/v1/monitoring/restart/node_exporter", headers=headers
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_exporter_restart_error(client, headers):
    with patch(
        "dawos_agent.routers.monitoring_router.monitoring.exporter_restart",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/monitoring/restart/bad", headers=headers)
    assert resp.status_code == 500
