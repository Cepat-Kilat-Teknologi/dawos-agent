"""Tests for system info and metrics endpoints."""

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
